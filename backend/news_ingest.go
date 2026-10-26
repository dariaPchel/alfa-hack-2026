package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"strconv"
	"strings"
	"time"
)

var relativeDate = regexp.MustCompile(`(?i)(\d+)\s*(minute|hour|day|week|month)s?\s*ago`)
var russianRelativeDate = regexp.MustCompile(`(?i)(\d+)\s*(минут|час|дн|недел|месяц|год)`)

func parseNewsDate(value string, now time.Time) (time.Time, bool) {
	for _, layout := range []string{time.RFC3339, time.RFC1123Z, "2006-01-02", "Jan 2, 2006", "02.01.2006"} {
		if parsed, err := time.Parse(layout, value); err == nil {
			return parsed.UTC(), true
		}
	}
	match := relativeDate.FindStringSubmatch(value)
	if len(match) == 3 {
		n, _ := strconv.Atoi(match[1])
		unit := strings.ToLower(match[2])
		switch unit {
		case "minute":
			return now.Add(-time.Duration(n) * time.Minute), true
		case "hour":
			return now.Add(-time.Duration(n) * time.Hour), true
		case "day":
			return now.AddDate(0, 0, -n), true
		case "week":
			return now.AddDate(0, 0, -7*n), true
		case "month":
			return now.AddDate(0, -n, 0), true
		}
	}
	match = russianRelativeDate.FindStringSubmatch(value)
	if len(match) == 3 {
		n, _ := strconv.Atoi(match[1])
		unit := strings.ToLower(match[2])
		switch {
		case strings.HasPrefix(unit, "минут"):
			return now.Add(-time.Duration(n) * time.Minute), true
		case strings.HasPrefix(unit, "час"):
			return now.Add(-time.Duration(n) * time.Hour), true
		case strings.HasPrefix(unit, "дн"):
			return now.AddDate(0, 0, -n), true
		case strings.HasPrefix(unit, "недел"):
			return now.AddDate(0, 0, -7*n), true
		case strings.HasPrefix(unit, "месяц"):
			return now.AddDate(0, -n, 0), true
		case strings.HasPrefix(unit, "год"):
			return now.AddDate(-n, 0, 0), true
		}
	}
	return time.Time{}, false
}

func canonicalNewsURL(raw string) string {
	parsed, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || (parsed.Scheme != "https" && parsed.Scheme != "http") || parsed.Host == "" {
		return ""
	}
	parsed.RawQuery, parsed.Fragment = "", ""
	parsed.Host = strings.ToLower(parsed.Host)
	parsed.Path = strings.TrimSuffix(parsed.Path, "/")
	return parsed.String()
}

type serperItem struct {
	Title   string `json:"title"`
	Link    string `json:"link"`
	Snippet string `json:"snippet"`
	Source  string `json:"source"`
	Date    string `json:"date"`
}
type serperResponse struct {
	News []serperItem `json:"news"`
}

func fetchSerper(ctx context.Context, key, query string) ([]serperItem, error) {
	payload, _ := json.Marshal(map[string]any{"q": query, "num": 20, "tbs": "qdr:m3"})
	client := &http.Client{Timeout: 25 * time.Second}
	for attempt := 1; attempt <= 3; attempt++ {
		req, err := http.NewRequestWithContext(ctx, http.MethodPost, "https://google.serper.dev/news", bytes.NewReader(payload))
		if err != nil {
			return nil, err
		}
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-API-KEY", key)
		res, err := client.Do(req)
		if err == nil {
			body, readErr := io.ReadAll(io.LimitReader(res.Body, 2*1024*1024))
			res.Body.Close()
			if readErr != nil {
				return nil, readErr
			}
			if res.StatusCode == http.StatusOK {
				var response serperResponse
				if err := json.Unmarshal(body, &response); err != nil {
					return nil, err
				}
				return response.News, nil
			}
			if res.StatusCode != 429 && res.StatusCode < 500 {
				return nil, fmt.Errorf("news provider HTTP %d", res.StatusCode)
			}
			err = fmt.Errorf("news provider HTTP %d", res.StatusCode)
		}
		if attempt == 3 {
			return nil, err
		}
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(time.Duration(attempt) * time.Second):
		}
	}
	return nil, errors.New("news provider failed")
}

func (s *Store) upsertNews(ctx context.Context, companyID string, item NewsItem) error {
	if s.db == nil {
		return errors.New("PostgreSQL required for news ingestion")
	}
	payload, err := json.Marshal(item)
	if err != nil {
		return err
	}
	_, err = s.db.ExecContext(ctx, `INSERT INTO news_items(id,company_id,payload) VALUES($1,$2,$3)
 ON CONFLICT(id) DO UPDATE SET payload=EXCLUDED.payload, updated_at=now()`, item.ID, companyID, payload)
	if err == nil && s.redis != nil {
		_ = s.redis.Del(ctx, "news:"+companyID).Err()
	}
	return err
}

func refreshNews(ctx context.Context, s *Store) (int, error) {
	key := os.Getenv("SERPER_API_KEY")
	if key == "" {
		return 0, errors.New("SERPER_API_KEY is required for live news")
	}
	companies, err := s.CompaniesForRefresh(ctx, 20)
	if err != nil {
		return 0, err
	}
	return refreshCompanies(ctx, s, key, companies)
}

func refreshCompanies(ctx context.Context, s *Store, key string, companies []Company) (int, error) {
	total := 0
	var firstError error
	for _, company := range companies {
		if company.Industry == "" {
			continue
		}
		query := company.Industry + " " + company.Region + " новости"
		raw, err := fetchSerper(ctx, key, query)
		if err != nil {
			log.Printf("news refresh %s failed: %v", company.ID, err)
			if firstError == nil {
				firstError = err
			}
			continue
		}
		now := time.Now().UTC()
		for _, candidate := range raw {
			link := canonicalNewsURL(candidate.Link)
			published, ok := parseNewsDate(candidate.Date, now)
			if !ok || link == "" || candidate.Title == "" || published.After(now.Add(5*time.Minute)) || published.Before(now.AddDate(0, 0, -90)) {
				continue
			}
			hash := sha256.Sum256([]byte(company.ID + "|" + link))
			score := 0
			for term := range words(company.Industry + " " + company.Region) {
				if strings.Contains(strings.ToLower(candidate.Title+" "+candidate.Snippet), term) {
					score += 20
				}
			}
			if score == 0 {
				continue
			}
			if score > 100 {
				score = 100
			}
			item := NewsItem{
				ID: fmt.Sprintf("news-%x", hash[:12]), Title: candidate.Title, Text: candidate.Snippet,
				FullText: candidate.Snippet, URL: link, PublishedAt: published.Format(time.RFC3339), RetrievedAt: now.Format(time.RFC3339),
				Time: published.Format("15:04"), Source: candidate.Source, Category: "industry", Relevance: score, Impact: "unknown",
			}
			if err := s.upsertNews(ctx, company.ID, item); err != nil {
				return total, err
			}
			total++
		}
	}
	return total, firstError
}

func runNewsWorker(ctx context.Context, s *Store) error {
	interval := 6 * time.Hour
	if raw := os.Getenv("NEWS_REFRESH_INTERVAL"); raw != "" {
		parsed, err := time.ParseDuration(raw)
		if err != nil || parsed < time.Minute {
			return errors.New("NEWS_REFRESH_INTERVAL must be at least 1m")
		}
		interval = parsed
	}
	nextScheduled := time.Time{}
	for {
		if time.Now().After(nextScheduled) {
			count, err := refreshNews(ctx, s)
			if err != nil {
				log.Printf("scheduled news refresh failed: %v", err)
			} else {
				log.Printf("scheduled news refresh saved %d items", count)
			}
			nextScheduled = time.Now().Add(interval)
		}
		ids, err := s.PendingNewsRefresh(ctx)
		if err != nil {
			log.Printf("news refresh queue failed: %v", err)
		}
		for _, id := range ids {
			if err := s.SetNewsRefreshStatus(ctx, id, "running", ""); err != nil {
				log.Printf("news refresh status failed: %v", err)
				continue
			}
			key := os.Getenv("SERPER_API_KEY")
			var refreshErr error
			if key == "" {
				refreshErr = errors.New("SERPER_API_KEY is required")
			}
			var company Company
			if refreshErr == nil {
				company, refreshErr = s.GetCompany(ctx, id)
			}
			if refreshErr == nil {
				_, refreshErr = refreshCompanies(ctx, s, key, []Company{company})
			}
			status, errorMessage := "complete", ""
			if refreshErr != nil {
				status, errorMessage = "failed", refreshErr.Error()
			}
			if err := s.SetNewsRefreshStatus(ctx, id, status, errorMessage); err != nil {
				log.Printf("news refresh status failed: %v", err)
			}
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(15 * time.Second):
		}
	}
}
