package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestNewsWindowsExcludeUndatedAndOldItems(t *testing.T) {
	now := time.Now().UTC()
	items := []NewsItem{
		{ID: "fresh", PublishedAt: now.Add(-2 * time.Hour).Format(time.RFC3339), RetrievedAt: now.Format(time.RFC3339)},
		{ID: "week", PublishedAt: now.Add(-3 * 24 * time.Hour).Format(time.RFC3339), RetrievedAt: now.Format(time.RFC3339)},
		{ID: "old", PublishedAt: now.Add(-100 * 24 * time.Hour).Format(time.RFC3339)},
		{ID: "undated"},
	}
	for _, tc := range []struct {
		duration time.Duration
		want     int
	}{
		{24 * time.Hour, 1}, {7 * 24 * time.Hour, 2}, {90 * 24 * time.Hour, 2},
	} {
		got := window(items, tc.duration)["actual_count"].(int)
		if got != tc.want {
			t.Fatalf("duration %v: got %d want %d", tc.duration, got, tc.want)
		}
	}
}

func TestAnalysisQuestionIsRequired(t *testing.T) {
	api, _ := testAPI(t)
	payload, _ := json.Marshal(map[string]any{"event_ids": []string{"news-1"}})
	req := httptest.NewRequest(http.MethodPost, "/api/companies/U001/analyze", bytes.NewReader(payload))
	rec := httptest.NewRecorder()
	api.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("got %d, want 400", rec.Code)
	}
}

func TestPeerSelectionUsesRealProfileFeatures(t *testing.T) {
	target := Company{ID: "a", OKVED: "41.20", Region: "Москва", Revenue: "100"}
	candidates := []Company{
		target,
		{ID: "same-industry", OKVED: "41.11", Region: "Тула"},
		{ID: "same-region", OKVED: "50.01", Region: "Москва"},
		{ID: "unrelated", OKVED: "90.01", Region: "Казань"},
	}
	peers := selectPeers(target, candidates)
	if len(peers) != 2 || peers[0].Company.ID != "same-industry" {
		t.Fatalf("unexpected peers: %+v", peers)
	}
}

func TestRussianRelativeProviderDate(t *testing.T) {
	now := time.Date(2026, 10, 26, 12, 0, 0, 0, time.UTC)
	got, ok := parseNewsDate("2 дня назад", now)
	if !ok || got.Format("2006-01-02") != "2026-10-24" {
		t.Fatalf("relative Russian date: %v %v", got, ok)
	}
}

func TestSerperRussianCalendarDateAndBroadQuery(t *testing.T) {
	got, ok := parseNewsDate("10 авг. 2026 г.", time.Date(2026, 10, 26, 0, 0, 0, 0, time.UTC))
	if !ok || got.Format("2006-01-02") != "2026-08-10" {
		t.Fatalf("calendar date: %v %v", got, ok)
	}
	query := newsQuery(Company{OKVED: "46.90", Industry: "Торговля оптовая неспециализированная", Region: "Москва"})
	if query != "оптовая торговля новости" {
		t.Fatalf("news query too narrow: %q", query)
	}
}
func TestSemicolonCSVWithQuotedFields(t *testing.T) {
	path := filepath.Join(t.TempDir(), "companies.csv")
	content := "SYNTHETIC_U;MAINOKVED_NAME;CL_PRODUCT_RKO_MARK\nU_1;\"Торговля, услуги\";1.0\n"
	if err := os.WriteFile(path, []byte(content), 0600); err != nil {
		t.Fatal(err)
	}
	var industry string
	err := scanCSV(path, []string{"SYNTHETIC_U", "MAINOKVED_NAME"}, func(cols map[string]int, row []string) error {
		industry = field(cols, row, "MAINOKVED_NAME")
		if numeric(field(cols, row, "CL_PRODUCT_RKO_MARK")) != 1 {
			t.Fatal("numeric marker not parsed")
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if industry != "Торговля, услуги" {
		t.Fatalf("industry=%q", industry)
	}
}

func TestSuppliedCSVShapes(t *testing.T) {
	root := os.Getenv("ALFA_DATA_DIR")
	if root == "" {
		t.Skip("set ALFA_DATA_DIR to validate supplied files")
	}
	cases := []struct {
		name     string
		required []string
		minRows  int
	}{
		{"df_Uid_data_hack.csv", []string{"SYNTHETIC_U", "MAINOKVED_CODE", "REVENUE_COMPANY"}, 80000},
		{"df_Fid_Uid_link_hack.csv", []string{"SYNTHETIC_U", "SYNTHETIC_F"}, 12000},
		{"df_Uid_payment_hack.csv", []string{"BENEFICIARY", "PAYER", "PAY_AMT", "PAY_CNT"}, 1300000},
	}
	for _, tc := range cases {
		count := 0
		err := scanCSV(filepath.Join(root, tc.name), tc.required, func(cols map[string]int, row []string) error {
			count++
			if count == 1 && field(cols, row, tc.required[0]) == "" {
				t.Fatalf("%s first row empty", tc.name)
			}
			return nil
		})
		if err != nil {
			t.Fatal(err)
		}
		if count < tc.minRows {
			t.Fatalf("%s: got %d rows", tc.name, count)
		}
	}
}
