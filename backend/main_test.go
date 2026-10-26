package main

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func testAPI(t *testing.T) (*API, *Store) {
	t.Helper()
	t.Setenv("DEMO_SEED", "true")
	store := &Store{useMemory: true, memory: memoryState{news: make(map[string][]NewsItem), jobs: make(map[string]Analysis), analyses: make(map[string]Analysis)}}
	store.seedMemory()
	return NewAPI(store, nil), store
}

func TestDemoAPIHealthAndNews(t *testing.T) {
	api, _ := testAPI(t)
	handler := api.Handler()
	for _, path := range []string{"/healthz", "/api/companies/U001/news"} {
		request := httptest.NewRequest(http.MethodGet, path, nil)
		recorder := httptest.NewRecorder()
		handler.ServeHTTP(recorder, request)
		if recorder.Code != http.StatusOK {
			t.Fatalf("%s status: %d", path, recorder.Code)
		}
	}
}

func TestDemoAPIAnalysisLifecycle(t *testing.T) {
	api, _ := testAPI(t)
	handler := api.Handler()
	body, _ := json.Marshal(map[string]any{"event_ids": []string{"news-1"}, "question": "Как это повлияет на компанию?"})
	request := httptest.NewRequest(http.MethodPost, "/api/companies/U001/analyze", bytes.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusAccepted {
		t.Fatalf("analyze status: %d", recorder.Code)
	}
	var accepted struct {
		AnalysisID string `json:"analysis_id"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &accepted); err != nil || accepted.AnalysisID == "" {
		t.Fatalf("accepted response: err=%v id=%q", err, accepted.AnalysisID)
	}
}

func TestP1WorkerProcessing(t *testing.T) {
	t.Setenv("DEMO_SEED", "true")
	_, store := testAPI(t)
	job := Analysis{ID: "analysis-test", CompanyID: "U001", EventID: "news-1", Status: "queued"}
	if err := store.CreateJob(context.Background(), job); err != nil {
		t.Fatal(err)
	}
	if err := processAnalysis(context.Background(), store, nil, AnalysisRequested{AnalysisID: job.ID, CompanyID: job.CompanyID, EventID: job.EventID}); err != nil {
		t.Fatal(err)
	}
	result, err := store.GetAnalysis(context.Background(), job.ID)
	if err != nil {
		t.Fatal(err)
	}
	if result.Status != "complete" || result.Provenance != "go-worker-demo" {
		t.Fatalf("unexpected analysis: %+v", result)
	}
}
