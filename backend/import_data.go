package main

import (
	"bufio"
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/csv"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"strconv"
	"strings"
)

type paymentSummary struct {
	InAmount  float64
	OutAmount float64
	InCount   int
	OutCount  int
}

func scanCSV(path string, required []string, visit func(map[string]int, []string) error) error {
	file, err := os.Open(path)
	if err != nil {
		return err
	}
	defer file.Close()
	first, err := bufio.NewReader(file).ReadString('\n')
	if err != nil && !errors.Is(err, io.EOF) {
		return err
	}
	if _, err := file.Seek(0, 0); err != nil {
		return err
	}
	reader := csv.NewReader(bufio.NewReaderSize(file, 128*1024))
	if strings.Count(first, ";") > strings.Count(first, ",") {
		reader.Comma = ';'
	}
	reader.FieldsPerRecord = -1
	reader.LazyQuotes = true
	headers, err := reader.Read()
	if err != nil {
		return err
	}
	columns := map[string]int{}
	for i, name := range headers {
		columns[strings.TrimSpace(strings.TrimPrefix(name, "\uFEFF"))] = i
	}
	for _, name := range required {
		if _, ok := columns[name]; !ok {
			return fmt.Errorf("%s: missing column %s", path, name)
		}
	}
	for {
		row, err := reader.Read()
		if errors.Is(err, io.EOF) {
			return nil
		}
		if err != nil {
			return fmt.Errorf("%s: %w", path, err)
		}
		if err := visit(columns, row); err != nil {
			return err
		}
	}
}

func field(columns map[string]int, row []string, name string) string {
	i, ok := columns[name]
	if !ok || i >= len(row) {
		return ""
	}
	return strings.TrimSpace(row[i])
}

func numeric(value string) float64 {
	n, _ := strconv.ParseFloat(strings.ReplaceAll(value, ",", "."), 64)
	return n
}

func checksumFiles(paths ...string) (string, error) {
	hash := sha256.New()
	for _, path := range paths {
		if path == "" {
			continue
		}
		file, err := os.Open(path)
		if err != nil {
			return "", err
		}
		if _, err := io.Copy(hash, file); err != nil {
			file.Close()
			return "", err
		}
		file.Close()
	}
	return fmt.Sprintf("%x", hash.Sum(nil)), nil
}

func importCompanies(ctx context.Context, store *Store) (int, error) {
	if store.db == nil {
		return 0, errors.New("PostgreSQL required for import")
	}
	path := os.Getenv("COMPANIES_CSV")
	if path == "" {
		return 0, errors.New("COMPANIES_CSV is required")
	}
	checksum, err := checksumFiles(path, os.Getenv("COMPANY_LINKS_CSV"), os.Getenv("COMPANY_PAYMENTS_CSV"))
	if err != nil {
		return 0, err
	}
	scoped := sha256.Sum256([]byte(checksum + "|" + envString("DATASET_KIND", "anonymized")))
	checksum = fmt.Sprintf("%x", scoped[:])
	var previous string
	var previousCount int
	err = store.db.QueryRowContext(ctx, `SELECT content_hash,record_count FROM dataset_imports WHERE name='companies'`).Scan(&previous, &previousCount)
	if err == nil && previous == checksum {
		return previousCount, nil
	}
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		return 0, err
	}
	linkCounts := map[string]int{}
	if linkPath := os.Getenv("COMPANY_LINKS_CSV"); linkPath != "" {
		err := scanCSV(linkPath, []string{"SYNTHETIC_U"}, func(cols map[string]int, row []string) error {
			id := field(cols, row, "SYNTHETIC_U")
			if id != "" {
				linkCounts[id]++
			}
			return nil
		})
		if err != nil {
			return 0, err
		}
	}
	payments := map[string]*paymentSummary{}
	if paymentPath := os.Getenv("COMPANY_PAYMENTS_CSV"); paymentPath != "" {
		err := scanCSV(paymentPath, []string{"BENEFICIARY", "PAYER", "PAY_AMT", "PAY_CNT"}, func(cols map[string]int, row []string) error {
			beneficiary, payer := field(cols, row, "BENEFICIARY"), field(cols, row, "PAYER")
			amount, count := numeric(field(cols, row, "PAY_AMT")), int(numeric(field(cols, row, "PAY_CNT")))
			if beneficiary != "" {
				p := payments[beneficiary]
				if p == nil {
					p = &paymentSummary{}
					payments[beneficiary] = p
				}
				p.InAmount += amount
				p.InCount += count
			}
			if payer != "" {
				p := payments[payer]
				if p == nil {
					p = &paymentSummary{}
					payments[payer] = p
				}
				p.OutAmount += amount
				p.OutCount += count
			}
			return nil
		})
		if err != nil {
			return 0, err
		}
	}
	count := 0
	seen := map[string]bool{}
	ambiguous := map[string]bool{}
	batch := make([]Company, 0, 200)
	flush := func() error {
		if len(batch) == 0 {
			return nil
		}
		var sqlText strings.Builder
		sqlText.WriteString("INSERT INTO companies(id,payload) VALUES ")
		args := make([]any, 0, len(batch)*2)
		kept := 0
		for _, company := range batch {
			if ambiguous[company.ID] {
				continue
			}
			if kept > 0 {
				sqlText.WriteByte(',')
			}
			sqlText.WriteString(fmt.Sprintf("($%d,$%d)", kept*2+1, kept*2+2))
			kept++
			payload, err := json.Marshal(company)
			if err != nil {
				return err
			}
			args = append(args, company.ID, payload)
		}
		if kept > 0 {
			sqlText.WriteString(" ON CONFLICT(id) DO UPDATE SET payload=EXCLUDED.payload, updated_at=now()")
			if _, err := store.db.ExecContext(ctx, sqlText.String(), args...); err != nil {
				return err
			}
			count += kept
		}
		batch = batch[:0]
		return nil
	}
	err = scanCSV(path, []string{"SYNTHETIC_U", "MAINOKVED_CODE", "MAINOKVED_NAME"}, func(cols map[string]int, row []string) error {
		id := field(cols, row, "SYNTHETIC_U")
		if id == "" {
			return nil
		}
		if seen[id] {
			ambiguous[id] = true
			return nil
		}
		seen[id] = true
		products := []string{}
		for _, product := range []struct{ column, name string }{
			{"CL_PRODUCT_RKO_MARK", "РКО"}, {"CL_PRODUCT_GAR_MARK", "Гарантии"},
			{"CL_PRODUCT_LOA_MARK", "Кредит"}, {"CL_PRODUCT_LEA_MARK", "Лизинг"},
			{"CL_PRODUCT_DEP_MARK", "Депозит"}, {"CL_PRODUCT_ZPP_MARK", "Зарплатный проект"},
		} {
			if numeric(field(cols, row, product.column)) > 0 {
				products = append(products, product.name)
			}
		}
		pay := payments[id]
		if pay == nil {
			pay = &paymentSummary{}
		}
		company := Company{
			ID: id, Name: "Обезличенная компания " + id, Industry: field(cols, row, "MAINOKVED_NAME"),
			OKVED: field(cols, row, "MAINOKVED_CODE"), Revenue: field(cols, row, "REVENUE_COMPANY"),
			RevenueAmount: numeric(field(cols, row, "REVENUE_COMPANY")), Region: field(cols, row, "REGION"),
			Employees: field(cols, row, "AMOUNT_WORKERS_FNS_GRADATION"), Products: products,
			GroupID: field(cols, row, "GROUP_ID"), RiskProfile: field(cols, row, "NEGATIVEMARK"),
			CounterpartyCount: linkCounts[id], PaymentAmount: pay.InAmount + pay.OutAmount,
			PaymentCount: pay.InCount + pay.OutCount, InboundPaymentAmount: pay.InAmount,
			OutboundPaymentAmount: pay.OutAmount, InboundPaymentCount: pay.InCount,
			OutboundPaymentCount: pay.OutCount, DatasetKind: envString("DATASET_KIND", "anonymized"),
		}
		batch = append(batch, company)
		if len(batch) >= 200 {
			return flush()
		}
		return nil
	})
	if err != nil {
		return count, err
	}
	if err := flush(); err != nil {
		return count, err
	}
	for id := range ambiguous {
		_, err := store.db.ExecContext(ctx, `DELETE FROM companies
          WHERE id=$1 AND payload->>'datasetKind'='anonymized'`, id)
		if err != nil {
			return count, err
		}
	}
	count = len(seen) - len(ambiguous)
	if len(ambiguous) > 0 {
		log.Printf("excluded %d ambiguous company IDs", len(ambiguous))
	}
	_, err = store.db.ExecContext(ctx, `INSERT INTO dataset_imports(name,content_hash,record_count)
      VALUES('companies',$1,$2) ON CONFLICT(name) DO UPDATE SET content_hash=EXCLUDED.content_hash,
      record_count=EXCLUDED.record_count,imported_at=now()`, checksum, count)
	if err != nil {
		return count, err
	}
	return count, nil
}

func importResearch(ctx context.Context, store *Store) (int, error) {
	if store.db == nil {
		return 0, errors.New("PostgreSQL required for import")
	}
	path := os.Getenv("BANK_RESEARCH_JSONL")
	if path == "" {
		return 0, errors.New("BANK_RESEARCH_JSONL is required")
	}
	file, err := os.Open(path)
	if err != nil {
		return 0, err
	}
	defer file.Close()
	decoder := json.NewDecoder(file)
	count := 0
	for {
		var doc ResearchDoc
		if err := decoder.Decode(&doc); errors.Is(err, io.EOF) {
			break
		} else if err != nil {
			return count, err
		}
		if doc.Title == "" || !validHTTPURL(doc.URL) || doc.Page < 1 || strings.TrimSpace(doc.Content) == "" {
			return count, fmt.Errorf("invalid research document at record %d", count+1)
		}
		if doc.ID == "" {
			sum := sha256.Sum256([]byte(fmt.Sprintf("%s|%s|%d", doc.Title, doc.URL, doc.Page)))
			doc.ID = fmt.Sprintf("research-%x", sum[:8])
		}
		_, err := store.db.ExecContext(ctx, `INSERT INTO bank_research(id,title,url,page,content) VALUES($1,$2,$3,$4,$5)
   ON CONFLICT(id) DO UPDATE SET title=EXCLUDED.title,url=EXCLUDED.url,page=EXCLUDED.page,content=EXCLUDED.content,updated_at=now()`,
			doc.ID, doc.Title, doc.URL, doc.Page, doc.Content)
		if err != nil {
			return count, err
		}
		count++
	}
	return count, nil
}
