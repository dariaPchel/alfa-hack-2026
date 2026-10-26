package main

import (
	"context"
	"database/sql"
	"embed"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/stdlib"
	"github.com/redis/go-redis/v9"
)

//go:embed migrations/001_init.sql
var schemaSQL embed.FS

type Store struct {
	db        *sql.DB
	redis     *redis.Client
	useMemory bool
	mu        sync.RWMutex
	memory    memoryState
}

type memoryState struct {
	companies []Company
	news      map[string][]NewsItem
	jobs      map[string]Analysis
	analyses  map[string]Analysis
}

func NewStore(ctx context.Context) (*Store, error) {
	store := &Store{memory: memoryState{news: make(map[string][]NewsItem), jobs: make(map[string]Analysis), analyses: make(map[string]Analysis)}}
	dsn := strings.TrimSpace(os.Getenv("DATABASE_URL"))
	if dsn == "" {
		if !envBool("DEMO_SEED", false) {
			return nil, fmt.Errorf("DATABASE_URL is required; set DEMO_SEED=true only for local demo")
		}
		store.useMemory = true
		store.seedMemory()
		return store, nil
	}
	db := stdlib.OpenDB(*mustParseConfig(dsn))
	if err := db.PingContext(ctx); err != nil {
		db.Close()
		if envBool("DEMO_SEED", false) {
			store.useMemory = true
			store.seedMemory()
			return store, nil
		}
		return nil, fmt.Errorf("postgres ping: %w", err)
	}
	store.db = db
	if err := store.migrate(ctx); err != nil {
		db.Close()
		return nil, err
	}
	if envBool("DEMO_SEED", false) {
		if err := store.seedDatabase(ctx); err != nil {
			db.Close()
			return nil, err
		}
	}
	if addr := strings.TrimSpace(os.Getenv("REDIS_ADDR")); addr != "" {
		client := redis.NewClient(&redis.Options{Addr: addr, Password: os.Getenv("REDIS_PASSWORD"), DB: 0})
		if err := client.Ping(ctx).Err(); err != nil {
			client.Close()
			if !envBool("DEMO_SEED", false) {
				db.Close()
				return nil, fmt.Errorf("redis ping: %w", err)
			}
		} else {
			store.redis = client
		}
	}
	return store, nil
}

func mustParseConfig(dsn string) *pgx.ConnConfig {
	config, err := pgx.ParseConfig(dsn)
	if err != nil {
		panic(fmt.Sprintf("invalid DATABASE_URL: %v", err))
	}
	return config
}

func (s *Store) migrate(ctx context.Context) error {
	schema, err := schemaSQL.ReadFile("migrations/001_init.sql")
	if err != nil {
		return fmt.Errorf("read schema: %w", err)
	}
	for _, statement := range strings.Split(string(schema), ";") {
		statement = strings.TrimSpace(statement)
		if statement == "" {
			continue
		}
		if _, err := s.db.ExecContext(ctx, statement); err != nil {
			return fmt.Errorf("migrate postgres: %w", err)
		}
	}
	return nil
}

func (s *Store) Close() error {
	if s.redis != nil {
		_ = s.redis.Close()
	}
	if s.db != nil {
		return s.db.Close()
	}
	return nil
}

func (s *Store) Mode() string {
	if s.useMemory {
		return "memory-demo"
	}
	if envBool("DEMO_SEED", false) {
		return "postgres-demo"
	}
	return "postgres"
}

func (s *Store) ListCompanies(ctx context.Context) ([]Company, error) {
	if s.useMemory {
		s.mu.RLock()
		defer s.mu.RUnlock()
		return append([]Company(nil), s.memory.companies...), nil
	}
	rows, err := s.db.QueryContext(ctx, `SELECT payload FROM companies ORDER BY id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var result []Company
	for rows.Next() {
		var payload []byte
		if err := rows.Scan(&payload); err != nil {
			return nil, err
		}
		var company Company
		if err := json.Unmarshal(payload, &company); err != nil {
			return nil, err
		}
		result = append(result, company)
	}
	return result, rows.Err()
}

func (s *Store) ListNews(ctx context.Context, companyID string) ([]NewsItem, error) {
	cacheKey := "news:" + companyID
	if s.redis != nil {
		if cached, err := s.redis.Get(ctx, cacheKey).Bytes(); err == nil {
			var result []NewsItem
			if json.Unmarshal(cached, &result) == nil {
				return result, nil
			}
		}
	}
	if s.useMemory {
		s.mu.RLock()
		result := append([]NewsItem(nil), s.memory.news[companyID]...)
		s.mu.RUnlock()
		return result, nil
	}
	rows, err := s.db.QueryContext(ctx, `SELECT payload FROM news_items WHERE company_id=$1 ORDER BY created_at DESC`, companyID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var result []NewsItem
	for rows.Next() {
		var payload []byte
		if err := rows.Scan(&payload); err != nil {
			return nil, err
		}
		var item NewsItem
		if err := json.Unmarshal(payload, &item); err != nil {
			return nil, err
		}
		result = append(result, item)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	if s.redis != nil {
		if encoded, err := json.Marshal(result); err == nil {
			_ = s.redis.Set(ctx, cacheKey, encoded, 5*time.Minute).Err()
		}
	}
	return result, nil
}

func (s *Store) GetNews(ctx context.Context, companyID, eventID string) (NewsItem, error) {
	items, err := s.ListNews(ctx, companyID)
	if err != nil {
		return NewsItem{}, err
	}
	for _, item := range items {
		if item.ID == eventID {
			return item, nil
		}
	}
	return NewsItem{}, sql.ErrNoRows
}

func (s *Store) CreateJob(ctx context.Context, job Analysis) error {
	if s.useMemory {
		s.mu.Lock()
		if _, exists := s.memory.jobs[job.ID]; !exists {
			s.memory.jobs[job.ID] = job
		}
		s.mu.Unlock()
		return nil
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if _, err = tx.ExecContext(ctx, `INSERT INTO analysis_jobs(id, company_id, event_id, status, question) VALUES($1,$2,$3,$4,$5) ON CONFLICT (id) DO NOTHING`, job.ID, job.CompanyID, job.EventID, job.Status, job.Question); err != nil {
		return err
	}
	if _, err = tx.ExecContext(ctx, `INSERT INTO analysis_outbox(analysis_id) VALUES($1) ON CONFLICT DO NOTHING`, job.ID); err != nil {
		return err
	}
	return tx.Commit()
}

func (s *Store) SetJobStatus(ctx context.Context, id, status, errorMessage string) error {
	if s.useMemory {
		s.mu.Lock()
		job, ok := s.memory.jobs[id]
		if ok {
			job.Status, job.UpdatedAt = status, time.Now().UTC().Format(time.RFC3339)
			if status == "running" {
				job.Attempts++
			}
			job.Error = errorMessage
			s.memory.jobs[id] = job
		}
		s.mu.Unlock()
		return nil
	}
	_, err := s.db.ExecContext(ctx, `UPDATE analysis_jobs SET status=$2, error_message=$3, attempts=attempts+CASE WHEN $2='running' THEN 1 ELSE 0 END, updated_at=now() WHERE id=$1`, id, status, errorMessage)
	if s.redis != nil {
		_ = s.redis.Del(ctx, "analysis:"+id).Err()
	}
	return err
}

func (s *Store) SaveAnalysis(ctx context.Context, analysis Analysis) error {
	payload, err := json.Marshal(analysis)
	if err != nil {
		return err
	}
	if s.useMemory {
		s.mu.Lock()
		s.memory.analyses[analysis.ID] = analysis
		s.memory.jobs[analysis.ID] = analysis
		s.mu.Unlock()
		s.cacheAnalysis(ctx, analysis)
		return nil
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if _, err = tx.ExecContext(ctx, `INSERT INTO analyses(id, company_id, event_id, payload) VALUES($1,$2,$3,$4) ON CONFLICT (id) DO UPDATE SET payload=EXCLUDED.payload, updated_at=now()`, analysis.ID, analysis.CompanyID, analysis.EventID, payload); err != nil {
		return err
	}
	if _, err = tx.ExecContext(ctx, `UPDATE analysis_jobs SET status=$2, error_message=$3, updated_at=now() WHERE id=$1`, analysis.ID, analysis.Status, analysis.Error); err != nil {
		return err
	}
	if err = tx.Commit(); err != nil {
		return err
	}
	s.cacheAnalysis(ctx, analysis)
	return nil
}

func (s *Store) GetAnalysis(ctx context.Context, id string) (Analysis, error) {
	if s.redis != nil {
		if cached, err := s.redis.Get(ctx, "analysis:"+id).Bytes(); err == nil {
			var result Analysis
			if json.Unmarshal(cached, &result) == nil {
				return result, nil
			}
		}
	}
	if s.useMemory {
		s.mu.RLock()
		result, ok := s.memory.analyses[id]
		if !ok {
			result, ok = s.memory.jobs[id]
		}
		s.mu.RUnlock()
		if !ok {
			return Analysis{}, sql.ErrNoRows
		}
		return result, nil
	}
	var payload []byte
	err := s.db.QueryRowContext(ctx, `SELECT payload FROM analyses WHERE id=$1`, id).Scan(&payload)
	if errors.Is(err, sql.ErrNoRows) {
		var result Analysis
		var status, companyID, eventID, question, createdAt, updatedAt string
		var attempts int
		var errorMessage sql.NullString
		err = s.db.QueryRowContext(ctx, `SELECT status, company_id, event_id, question, error_message, attempts, created_at::text, updated_at::text FROM analysis_jobs WHERE id=$1`, id).Scan(&status, &companyID, &eventID, &question, &errorMessage, &attempts, &createdAt, &updatedAt)
		if err != nil {
			return Analysis{}, err
		}
		result = Analysis{ID: id, CompanyID: companyID, EventID: eventID, Question: question, Status: status, Error: errorMessage.String, Attempts: attempts, CreatedAt: createdAt, UpdatedAt: updatedAt}
		return result, nil
	}
	if err != nil {
		return Analysis{}, err
	}
	var result Analysis
	if err := json.Unmarshal(payload, &result); err != nil {
		return Analysis{}, err
	}
	return result, nil
}

func (s *Store) cacheAnalysis(ctx context.Context, analysis Analysis) {
	if s.redis == nil {
		return
	}
	if encoded, err := json.Marshal(analysis); err == nil {
		_ = s.redis.Set(ctx, "analysis:"+analysis.ID, encoded, 30*time.Minute).Err()
	}
}

func (s *Store) seedMemory() {
	companies, news := demoData()
	s.memory.companies, s.memory.news = companies, news
}

func (s *Store) seedDatabase(ctx context.Context) error {
	companies, news := demoData()
	for _, company := range companies {
		payload, _ := json.Marshal(company)
		if _, err := s.db.ExecContext(ctx, `INSERT INTO companies(id,payload) VALUES($1,$2) ON CONFLICT(id) DO UPDATE SET payload=EXCLUDED.payload, updated_at=now()`, company.ID, payload); err != nil {
			return err
		}
		for _, item := range news[company.ID] {
			item.PublishedAt = time.Now().UTC().Format(time.RFC3339)
			itemPayload, _ := json.Marshal(item)
			if _, err := s.db.ExecContext(ctx, `INSERT INTO news_items(id,company_id,payload) VALUES($1,$2,$3) ON CONFLICT(id) DO UPDATE SET payload=EXCLUDED.payload, updated_at=now()`, item.ID, company.ID, itemPayload); err != nil {
				return err
			}
		}
	}
	return nil
}

func envBool(name string, fallback bool) bool {
	value := strings.ToLower(strings.TrimSpace(os.Getenv(name)))
	if value == "" {
		return fallback
	}
	return value == "1" || value == "true" || value == "yes"
}

func (s *Store) PendingOutbox(ctx context.Context) ([]AnalysisRequested, error) {
	if s.db == nil {
		return nil, nil
	}
	rows, err := s.db.QueryContext(ctx, `SELECT j.id, j.company_id, j.event_id, j.question
        FROM analysis_outbox o JOIN analysis_jobs j ON j.id=o.analysis_id
        WHERE o.published_at IS NULL ORDER BY o.created_at LIMIT 100`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var requests []AnalysisRequested
	for rows.Next() {
		var request AnalysisRequested
		if err := rows.Scan(&request.AnalysisID, &request.CompanyID, &request.EventID, &request.Question); err != nil {
			return nil, err
		}
		requests = append(requests, request)
	}
	return requests, rows.Err()
}

func (s *Store) MarkOutboxPublished(ctx context.Context, id string) error {
	if s.db == nil {
		return nil
	}
	_, err := s.db.ExecContext(ctx, `UPDATE analysis_outbox SET published_at=now() WHERE analysis_id=$1`, id)
	return err
}

func (s *Store) SaveFeedback(ctx context.Context, analysisID, rating, comment string) error {
	if s.db == nil {
		return fmt.Errorf("feedback requires PostgreSQL")
	}
	_, err := s.db.ExecContext(ctx, `INSERT INTO analysis_feedback(analysis_id,rating,comment) VALUES($1,$2,$3)`,
		analysisID, rating, comment)
	return err
}

func (s *Store) CompanyExists(ctx context.Context, companyID string) (bool, error) {
	if s.useMemory {
		s.mu.RLock()
		defer s.mu.RUnlock()
		for _, company := range s.memory.companies {
			if company.ID == companyID {
				return true, nil
			}
		}
		return false, nil
	}
	var exists bool
	err := s.db.QueryRowContext(ctx, `SELECT EXISTS(SELECT 1 FROM companies WHERE id=$1)`, companyID).Scan(&exists)
	return exists, err
}

func (s *Store) RetryJob(ctx context.Context, id string) error {
	if s.db == nil {
		return fmt.Errorf("retry requires PostgreSQL")
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	var status string
	if err := tx.QueryRowContext(ctx, `SELECT status FROM analysis_jobs WHERE id=$1 FOR UPDATE`, id).Scan(&status); err != nil {
		return err
	}
	if status != "failed" && status != "complete" {
		return fmt.Errorf("only failed or completed jobs can be replayed")
	}
	if status == "failed" {
		if _, err := tx.ExecContext(ctx, `UPDATE analysis_jobs SET status='queued', error_message=NULL, updated_at=now() WHERE id=$1`, id); err != nil {
			return err
		}
	}
	if _, err := tx.ExecContext(ctx, `INSERT INTO analysis_outbox(analysis_id,published_at) VALUES($1,NULL)
        ON CONFLICT(analysis_id) DO UPDATE SET published_at=NULL`, id); err != nil {
		return err
	}
	if err := tx.Commit(); err != nil {
		return err
	}
	if s.redis != nil {
		_ = s.redis.Del(ctx, "analysis:"+id).Err()
	}
	return nil
}

func (s *Store) GetCompany(ctx context.Context, id string) (Company, error) {
	if s.useMemory {
		s.mu.RLock()
		defer s.mu.RUnlock()
		for _, company := range s.memory.companies {
			if company.ID == id {
				return company, nil
			}
		}
		return Company{}, sql.ErrNoRows
	}
	var payload []byte
	if err := s.db.QueryRowContext(ctx, "SELECT payload FROM companies WHERE id=$1 AND ($2 OR coalesce(payload->>'datasetKind','')<>'demo')", id, envBool("DEMO_SEED", false)).Scan(&payload); err != nil {
		return Company{}, err
	}
	var company Company
	if err := json.Unmarshal(payload, &company); err != nil {
		return Company{}, err
	}
	return company, nil
}

func (s *Store) SearchCompanies(ctx context.Context, query string, limit int) ([]Company, error) {
	if limit < 1 || limit > 100 {
		limit = 50
	}
	query = strings.TrimSpace(query)
	if s.useMemory {
		s.mu.RLock()
		defer s.mu.RUnlock()
		result := []Company{}
		for _, company := range s.memory.companies {
			if query == "" || strings.Contains(strings.ToLower(company.ID+" "+company.Name+" "+company.Industry), strings.ToLower(query)) {
				result = append(result, company)
				if len(result) == limit {
					break
				}
			}
		}
		return result, nil
	}
	var rows *sql.Rows
	var err error
	if query == "" {
		rows, err = s.db.QueryContext(ctx, "SELECT payload FROM companies WHERE ($2 OR coalesce(payload->>'datasetKind','')<>'demo') ORDER BY id LIMIT $1", limit, envBool("DEMO_SEED", false))
	} else {
		rows, err = s.db.QueryContext(ctx, `SELECT payload FROM companies
   WHERE (id ILIKE $1 OR payload->>'industry' ILIKE $1 OR payload->>'region' ILIKE $1)
   AND ($3 OR coalesce(payload->>'datasetKind','')<>'demo')
   ORDER BY id LIMIT $2`, "%"+query+"%", limit, envBool("DEMO_SEED", false))
	}
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	result := []Company{}
	for rows.Next() {
		var payload []byte
		if err := rows.Scan(&payload); err != nil {
			return nil, err
		}
		var company Company
		if err := json.Unmarshal(payload, &company); err != nil {
			return nil, err
		}
		result = append(result, company)
	}
	return result, rows.Err()
}

func (s *Store) PeerCandidates(ctx context.Context, company Company) ([]Company, error) {
	if s.useMemory {
		return s.ListCompanies(ctx)
	}
	prefix := company.OKVED
	if len(prefix) > 2 {
		prefix = prefix[:2]
	}
	rows, err := s.db.QueryContext(ctx, `SELECT payload FROM companies WHERE id<>$1
  AND (left(payload->>'okved',2)=$2 OR payload->>'region'=$3)
  LIMIT 500`, company.ID, prefix, company.Region)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	candidates := []Company{}
	for rows.Next() {
		var payload []byte
		if err := rows.Scan(&payload); err != nil {
			return nil, err
		}
		var peer Company
		if err := json.Unmarshal(payload, &peer); err != nil {
			return nil, err
		}
		candidates = append(candidates, peer)
	}
	return candidates, rows.Err()
}

func (s *Store) CompaniesForRefresh(ctx context.Context, limit int) ([]Company, error) {
	if limit < 1 || limit > 100 {
		limit = 20
	}
	ids := splitCSV(os.Getenv("NEWS_COMPANY_IDS"))
	if len(ids) > 100 {
		return nil, fmt.Errorf("NEWS_COMPANY_IDS is limited to 100 companies")
	}
	if len(ids) > 0 {
		result := []Company{}
		for _, id := range ids {
			company, err := s.GetCompany(ctx, id)
			if err != nil {
				return nil, fmt.Errorf("NEWS_COMPANY_IDS %s: %w", id, err)
			}
			result = append(result, company)
		}
		return result, nil
	}
	return s.SearchCompanies(ctx, "", limit)
}

func (s *Store) RequestNewsRefresh(ctx context.Context, companyID string) error {
	if s.db == nil {
		return fmt.Errorf("news refresh requires PostgreSQL")
	}
	_, err := s.db.ExecContext(ctx, `INSERT INTO news_refresh_jobs(company_id,status) VALUES($1,'queued')
        ON CONFLICT(company_id) DO UPDATE SET status='queued', error_message=NULL, requested_at=now(), updated_at=now()`, companyID)
	return err
}

func (s *Store) PendingNewsRefresh(ctx context.Context) ([]string, error) {
	if s.db == nil {
		return nil, nil
	}
	rows, err := s.db.QueryContext(ctx, `SELECT company_id FROM news_refresh_jobs WHERE status='queued' ORDER BY requested_at LIMIT 20`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	ids := []string{}
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		ids = append(ids, id)
	}
	return ids, rows.Err()
}

func (s *Store) SetNewsRefreshStatus(ctx context.Context, companyID, status, errorMessage string) error {
	if s.db == nil {
		return nil
	}
	_, err := s.db.ExecContext(ctx, `UPDATE news_refresh_jobs SET status=$2,error_message=$3,updated_at=now() WHERE company_id=$1`, companyID, status, errorMessage)
	return err
}

func (s *Store) GetNewsRefreshStatus(ctx context.Context, companyID string) (map[string]string, error) {
	if s.db == nil {
		return map[string]string{}, nil
	}
	var status string
	var errorMessage sql.NullString
	var updatedAt string
	err := s.db.QueryRowContext(ctx, `SELECT status,error_message,updated_at::text FROM news_refresh_jobs WHERE company_id=$1`, companyID).Scan(&status, &errorMessage, &updatedAt)
	if errors.Is(err, sql.ErrNoRows) {
		return map[string]string{}, nil
	}
	if err != nil {
		return nil, err
	}
	return map[string]string{"status": status, "error": errorMessage.String, "updated_at": updatedAt}, nil
}

func (s *Store) QualityMetrics(ctx context.Context) (map[string]int, error) {
	metrics := map[string]int{"complete": 0, "failed": 0, "pending": 0, "news": 0, "useful": 0, "not_useful": 0}
	if s.db == nil {
		return metrics, nil
	}
	var complete, failed, pending, news, useful, notUseful int
	err := s.db.QueryRowContext(ctx, `SELECT
      count(*) FILTER(WHERE status='complete'),
      count(*) FILTER(WHERE status='failed'),
      count(*) FILTER(WHERE status IN ('queued','running'))
      FROM analysis_jobs`).Scan(&complete, &failed, &pending)
	if err != nil {
		return nil, err
	}
	err = s.db.QueryRowContext(ctx, `SELECT count(*) FROM news_items`).Scan(&news)
	if err != nil {
		return nil, err
	}
	err = s.db.QueryRowContext(ctx, `SELECT count(*) FILTER(WHERE rating='useful'),
      count(*) FILTER(WHERE rating='not_useful') FROM analysis_feedback`).Scan(&useful, &notUseful)
	if err != nil {
		return nil, err
	}
	metrics["complete"], metrics["failed"], metrics["pending"] = complete, failed, pending
	metrics["news"], metrics["useful"], metrics["not_useful"] = news, useful, notUseful
	return metrics, nil
}
