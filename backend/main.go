package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"
	"strings"
	"time"
)

type Company struct {
	ID                    string   `json:"id"`
	Name                  string   `json:"name"`
	Industry              string   `json:"industry"`
	OKVED                 string   `json:"okved"`
	Revenue               string   `json:"revenue"`
	RevenueAmount         float64  `json:"revenueAmount,omitempty"`
	Region                string   `json:"region"`
	Employees             string   `json:"employees"`
	Products              []string `json:"products"`
	RiskProfile           string   `json:"riskProfile"`
	KeyRateExposure       string   `json:"keyRateExposure"`
	GroupID               string   `json:"groupId,omitempty"`
	CounterpartyCount     int      `json:"counterpartyCount,omitempty"`
	PaymentAmount         float64  `json:"paymentAmount,omitempty"`
	PaymentCount          int      `json:"paymentCount,omitempty"`
	InboundPaymentAmount  float64  `json:"inboundPaymentAmount,omitempty"`
	OutboundPaymentAmount float64  `json:"outboundPaymentAmount,omitempty"`
	InboundPaymentCount   int      `json:"inboundPaymentCount,omitempty"`
	OutboundPaymentCount  int      `json:"outboundPaymentCount,omitempty"`
	DatasetKind           string   `json:"datasetKind,omitempty"`
}

type NewsItem struct {
	ID            string   `json:"id"`
	Title         string   `json:"title"`
	Text          string   `json:"text"`
	Time          string   `json:"time"`
	URL           string   `json:"url,omitempty"`
	PublishedAt   string   `json:"published_at,omitempty"`
	RetrievedAt   string   `json:"retrieved_at,omitempty"`
	Source        string   `json:"source"`
	Icon          string   `json:"icon"`
	Category      string   `json:"category"`
	Relevance     int      `json:"relevance"`
	Impact        string   `json:"impact"`
	FullText      string   `json:"fullText"`
	BankAnalysis  string   `json:"bankAnalysis"`
	Risks         []string `json:"risks"`
	Opportunities []string `json:"opportunities"`
}

type Citation struct {
	Source string `json:"source"`
	Title  string `json:"title"`
	URL    string `json:"url"`
}

type Analysis struct {
	ID            string     `json:"analysis_id"`
	CompanyID     string     `json:"company_id"`
	EventID       string     `json:"event_id"`
	Question      string     `json:"question,omitempty"`
	Status        string     `json:"status"`
	EventTitle    string     `json:"event_title"`
	BankView      string     `json:"bank_view"`
	AIAnalysis    string     `json:"ai_analysis"`
	Risks         []string   `json:"risks"`
	Opportunities []string   `json:"opportunities"`
	Solutions     []string   `json:"solutions"`
	Citations     []Citation `json:"citations"`
	Provenance    string     `json:"provenance"`
	CreatedAt     string     `json:"created_at"`
	UpdatedAt     string     `json:"updated_at"`
	Error         string     `json:"error,omitempty"`
	Trace         []string   `json:"trace,omitempty"`
	Attempts      int        `json:"attempts,omitempty"`
}

type API struct {
	store *Store
	bus   *Bus
}

func NewAPI(store *Store, bus *Bus) *API {
	return &API{store: store, bus: bus}
}

func (a *API) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", a.health)
	mux.HandleFunc("/api/quality", a.qualityHandler)
	mux.HandleFunc("/api/companies", a.companiesHandler)
	mux.HandleFunc("/api/companies/", a.companyHandler)
	mux.HandleFunc("/api/analyses/", a.analysisHandler)
	return mux
}

func (a *API) health(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "service": "go-api", "mode": a.store.Mode(), "queue": a.bus != nil})
}

func (a *API) companiesHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet || r.URL.Path != "/api/companies" {
		writeError(w, http.StatusMethodNotAllowed, "method_not_allowed", "GET is required")
		return
	}
	companies, err := a.store.SearchCompanies(r.Context(), r.URL.Query().Get("q"), 50)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "storage_error", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "companies": companies, "count": len(companies), "provenance": a.store.Mode()})
}

func (a *API) companyHandler(w http.ResponseWriter, r *http.Request) {
	parts := strings.Split(strings.Trim(strings.TrimPrefix(r.URL.Path, "/api/companies/"), "/"), "/")
	if len(parts) < 1 || parts[0] == "" {
		writeError(w, http.StatusBadRequest, "invalid_company_id", "company id is required")
		return
	}
	companyID := parts[0]
	if len(parts) == 2 && parts[1] == "news" && r.Method == http.MethodGet {
		a.newsList(w, r, companyID)
		return
	}
	if len(parts) == 3 && parts[1] == "news" && parts[2] == "refresh" && r.Method == http.MethodPost {
		a.requestNewsRefresh(w, r, companyID)
		return
	}
	if len(parts) == 3 && parts[1] == "news" && r.Method == http.MethodGet {
		a.newsEvent(w, r, companyID, parts[2])
		return
	}
	if len(parts) == 2 && parts[1] == "analyze" && r.Method == http.MethodPost {
		a.startAnalysis(w, r, companyID)
		return
	}
	writeError(w, http.StatusNotFound, "not_found", "route not found")
}

func (a *API) newsList(w http.ResponseWriter, r *http.Request, companyID string) {
	exists, err := a.store.CompanyExists(r.Context(), companyID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "storage_error", err.Error())
		return
	}
	if !exists {
		writeError(w, http.StatusNotFound, "company_not_found", "company was not found")
		return
	}
	items, err := a.store.ListNews(r.Context(), companyID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "storage_error", err.Error())
		return
	}
	refresh, err := a.store.GetNewsRefreshStatus(r.Context(), companyID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "storage_error", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "synthetic_id": companyID, "windows": map[string]any{"24h": window(items, 24*time.Hour), "7d": window(items, 7*24*time.Hour), "90d": window(items, 90*24*time.Hour)}, "refresh": refresh, "provenance": a.store.Mode()})
}

func (a *API) newsEvent(w http.ResponseWriter, r *http.Request, companyID, eventID string) {
	item, err := a.store.GetNews(r.Context(), companyID, eventID)
	if err != nil {
		if err == sql.ErrNoRows {
			writeError(w, http.StatusNotFound, "event_not_found", "event was not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "storage_error", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "event": item, "analysis_status": "not_analyzed", "provenance": a.store.Mode()})
}

func window(items []NewsItem, duration time.Duration) map[string]any {
	now := time.Now().UTC()
	filtered := make([]NewsItem, 0, len(items))
	var latest time.Time
	for _, item := range items {
		published, err := time.Parse(time.RFC3339, item.PublishedAt)
		if err != nil || published.After(now) || published.Before(now.Add(-duration)) {
			continue
		}
		filtered = append(filtered, item)
		if retrieved, err := time.Parse(time.RFC3339, item.RetrievedAt); err == nil && retrieved.After(latest) {
			latest = retrieved
		}
	}
	updatedAt := ""
	if !latest.IsZero() {
		updatedAt = latest.Format(time.RFC3339)
	}
	warnings := []string{}
	if len(filtered) == 0 {
		warnings = append(warnings, "no_dated_news_in_window")
	}
	return map[string]any{"events": filtered, "actual_count": len(filtered), "updated_at": updatedAt, "warnings": warnings}
}

func (a *API) startAnalysis(w http.ResponseWriter, r *http.Request, companyID string) {
	var payload struct {
		EventIDs []string `json:"event_ids"`
		Question string   `json:"question"`
	}
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil || len(payload.EventIDs) == 0 {
		writeError(w, http.StatusBadRequest, "invalid_event_ids", "event_ids must contain at least one event")
		return
	}
	event, err := a.store.GetNews(r.Context(), companyID, payload.EventIDs[0])
	if err != nil {
		if err == sql.ErrNoRows {
			writeError(w, http.StatusNotFound, "event_not_found", "event was not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "storage_error", err.Error())
		return
	}
	payload.Question = strings.TrimSpace(payload.Question)
	if payload.Question == "" || len([]rune(payload.Question)) > 2000 {
		writeError(w, http.StatusBadRequest, "invalid_question", "question must contain 1-2000 characters")
		return
	}
	if a.bus == nil && !envBool("DEMO_SEED", false) {
		writeError(w, http.StatusServiceUnavailable, "queue_unavailable", "Kafka is required")
		return
	}
	analysisID := fmt.Sprintf("analysis-%d", time.Now().UnixNano())
	now := time.Now().UTC().Format(time.RFC3339)
	job := Analysis{ID: analysisID, CompanyID: companyID, EventID: event.ID, Status: "queued", EventTitle: event.Title, Question: payload.Question, Provenance: a.store.Mode(), CreatedAt: now, UpdatedAt: now}
	if err := a.store.CreateJob(r.Context(), job); err != nil {
		writeError(w, http.StatusInternalServerError, "storage_error", err.Error())
		return
	}
	request := AnalysisRequested{AnalysisID: analysisID, CompanyID: companyID, EventID: event.ID, Question: payload.Question}
	if a.bus == nil {
		if !envBool("DEMO_SEED", false) {
			writeError(w, http.StatusServiceUnavailable, "queue_unavailable", "Kafka is required")
			return
		}
		go func() { _ = processAnalysis(context.Background(), a.store, nil, request) }()
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"success": true, "analysis_id": analysisID, "status": "queued", "provenance": a.store.Mode()})
}

func (a *API) analysisHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, "/feedback") {
		a.feedbackHandler(w, r)
		return
	}
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "method_not_allowed", "GET is required")
		return
	}
	id := strings.Trim(strings.TrimPrefix(r.URL.Path, "/api/analyses/"), "/")
	analysis, err := a.store.GetAnalysis(r.Context(), id)
	if err != nil {
		if err == sql.ErrNoRows {
			writeError(w, http.StatusNotFound, "analysis_not_found", "analysis was not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "storage_error", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "analysis": analysis})
}

func processAnalysis(ctx context.Context, store *Store, bus *Bus, request AnalysisRequested) error {
	current, err := store.GetAnalysis(ctx, request.AnalysisID)
	if err != nil {
		return err
	}
	if current.Status == "complete" {
		if bus != nil {
			return bus.PublishCompleted(ctx, current)
		}
		return nil
	}
	if err := store.SetJobStatus(ctx, request.AnalysisID, "running", ""); err != nil {
		return err
	}
	var result Analysis
	if envBool("DEMO_SEED", false) && request.CompanyID == "U001" {
		event, eventErr := store.GetNews(ctx, request.CompanyID, request.EventID)
		if eventErr != nil {
			err = eventErr
		} else {
			now := time.Now().UTC().Format(time.RFC3339)
			result = Analysis{
				ID: request.AnalysisID, CompanyID: request.CompanyID, EventID: request.EventID,
				Question: request.Question, Status: "complete", EventTitle: event.Title,
				BankView:   event.BankAnalysis,
				AIAnalysis: fmt.Sprintf("Демонстрационный шаблон для вопроса «%s». Событие: %s", request.Question, event.Text),
				Risks:      event.Risks, Opportunities: event.Opportunities,
				Solutions:  []string{"Проверить влияние события на текущий портфель проектов"},
				Provenance: "go-worker-demo", CreatedAt: now, UpdatedAt: now,
			}
		}
	} else {
		result, err = generateAnalysis(ctx, store, request)
	}
	if err != nil {
		if bus == nil {
			_ = store.SetJobStatus(ctx, request.AnalysisID, "failed", err.Error())
		}
		return err
	}
	if strings.TrimSpace(result.AIAnalysis) == "" || strings.TrimSpace(result.BankView) == "" {
		err = fmt.Errorf("analysis has no substantive result")
		if bus == nil {
			_ = store.SetJobStatus(ctx, request.AnalysisID, "failed", err.Error())
		}
		return err
	}
	if err := store.SaveAnalysis(ctx, result); err != nil {
		return err
	}
	if bus != nil {
		return bus.PublishCompleted(ctx, result)
	}
	return nil
}

func demoData() ([]Company, map[string][]NewsItem) {
	company := Company{ID: "U001", DatasetKind: "demo", Name: `ООО "Новое поколение"`, Industry: "Строительство", OKVED: "41.20 — Строительство жилых и нежилых зданий", Revenue: "18 500 000 000 ₽", Region: "Москва", Employees: "500–1000", Products: []string{"РКО", "Кредит", "Лизинг", "Зарплатный проект"}, RiskProfile: "Умеренный", KeyRateExposure: "Высокая (кредитный портфель 4.2 млрд ₽)"}
	items := []NewsItem{
		{ID: "news-1", Title: "ЦБ сохранил ключевую ставку", Text: "ЦБ сохранил ключевую ставку на уровне 21,0% годовых, решение принято 11 сентября.", Time: "12:25", Source: "Центральный Банк РФ", Icon: "cb", Category: "macro", Relevance: 95, Impact: "high", FullText: "Совет директоров Банка России принял решение сохранить ключевую ставку.", BankAnalysis: "Период быстрого удешевления кредитов временно приостановлен.", Risks: []string{"Удорожание обслуживания кредитного портфеля", "Снижение маржинальности строительных проектов"}, Opportunities: []string{"Фиксация текущих ставок по долгосрочным кредитам", "Пересмотр инвестиционной программы"}},
		{ID: "news-2", Title: "Рост стоимости строительных материалов", Text: "Рост стоимости строительных материалов может увеличить себестоимость жилых проектов", Time: "11:50", Source: "Альфа-Банк Аналитика", Icon: "industry", Category: "industry", Relevance: 88, Impact: "medium", FullText: "Индекс стоимости строительных материалов вырос на 4,3% за последний месяц.", BankAnalysis: "Рост себестоимости напрямую влияет на маржу.", Risks: []string{"Снижение рентабельности проектов", "Риск срыва сроков по фиксированным контрактам"}, Opportunities: []string{"Пересмотр ценовой политики", "Переход на альтернативных поставщиков"}},
		{ID: "news-3", Title: "Дефицит квалифицированных строительных кадров", Text: "Дефицит кадров может увеличить сроки сдачи объектов", Time: "10:11", Source: "Альфа-Банк Аналитика", Icon: "industry", Category: "industry", Relevance: 72, Impact: "medium", FullText: "Нехватка рабочих специальностей достигла исторического максимума.", BankAnalysis: "Кадровый дефицит создаёт операционные риски.", Risks: []string{"Срыв сроков сдачи объектов", "Рост ФОТ"}, Opportunities: []string{"Инвестиции в автоматизацию", "Программы обучения"}},
	}
	for i := range items {
		items[i].PublishedAt = time.Now().UTC().Format(time.RFC3339)
		items[i].RetrievedAt = items[i].PublishedAt
	}
	return []Company{company}, map[string][]NewsItem{company.ID: items}
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}
func writeError(w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, map[string]any{"success": false, "error_code": code, "message": message})
}

func main() {
	mode := flag.String("mode", "api", "api or worker")
	addr := envString("HTTP_ADDR", ":8080")
	flag.Parse()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	store, err := NewStore(ctx)
	if err != nil {
		log.Fatal(err)
	}
	defer store.Close()
	bus := NewBus()
	if *mode == "import-companies" {
		importCtx, stopImport := context.WithTimeout(context.Background(), 15*time.Minute)
		defer stopImport()
		count, err := importCompanies(importCtx, store)
		if err != nil {
			log.Fatal(err)
		}
		log.Printf("%d company profiles available", count)
		return
	}
	if *mode == "import-research" {
		importCtx, stopImport := context.WithTimeout(context.Background(), 15*time.Minute)
		defer stopImport()
		count, err := importResearch(importCtx, store)
		if err != nil {
			log.Fatal(err)
		}
		log.Printf("imported %d bank research fragments", count)
		return
	}
	if *mode == "news-worker" {
		log.Fatal(runNewsWorker(context.Background(), store))
	}
	if *mode == "retry-job" {
		id := strings.TrimSpace(envString("ANALYSIS_ID", ""))
		if id == "" {
			log.Fatal("ANALYSIS_ID is required")
		}
		if err := store.RetryJob(ctx, id); err != nil {
			log.Fatal(err)
		}
		log.Printf("requeued analysis %s", id)
		return
	}
	if *mode == "worker" {
		if bus == nil {
			log.Fatal("worker requires KAFKA_BROKERS")
		}
		defer bus.Close()
		log.Printf("go analysis worker started")
		log.Fatal(bus.RunWorker(context.Background(), func(ctx context.Context, request AnalysisRequested) error {
			return processAnalysis(ctx, store, bus, request)
		}, func(ctx context.Context, id string, processErr error) error {
			current, err := store.GetAnalysis(ctx, id)
			if err == nil && current.Status == "complete" {
				return nil
			}
			return store.SetJobStatus(ctx, id, "failed", processErr.Error())
		}))
	}
	defer bus.Close()
	if bus != nil {
		go dispatchOutbox(context.Background(), store, bus)
	}
	log.Printf("go API listening on %s", addr)
	log.Fatal(http.ListenAndServe(addr, NewAPI(store, bus).Handler()))
}

func dispatchOutbox(ctx context.Context, store *Store, bus *Bus) {
	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()
	for {
		pending, err := store.PendingOutbox(ctx)
		if err != nil {
			log.Printf("outbox query failed: %v", err)
		}
		for _, request := range pending {
			if err := bus.PublishRequested(ctx, request); err != nil {
				log.Printf("outbox publish failed: %v", err)
				break
			}
			if err := store.MarkOutboxPublished(ctx, request.AnalysisID); err != nil {
				log.Printf("outbox mark failed: %v", err)
				break
			}
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (a *API) feedbackHandler(w http.ResponseWriter, r *http.Request) {
	id := strings.TrimSuffix(strings.TrimPrefix(r.URL.Path, "/api/analyses/"), "/feedback")
	if id == "" || strings.Contains(id, "/") {
		writeError(w, http.StatusBadRequest, "invalid_analysis_id", "invalid analysis id")
		return
	}
	var payload struct {
		Rating  string `json:"rating"`
		Comment string `json:"comment"`
	}
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil ||
		(payload.Rating != "useful" && payload.Rating != "not_useful") || len([]rune(payload.Comment)) > 1000 {
		writeError(w, http.StatusBadRequest, "invalid_feedback", "rating must be useful or not_useful; comment max 1000 chars")
		return
	}
	analysis, err := a.store.GetAnalysis(r.Context(), id)
	if err != nil {
		writeError(w, http.StatusNotFound, "analysis_not_found", "analysis not found")
		return
	}
	if analysis.Status != "complete" {
		writeError(w, http.StatusConflict, "analysis_incomplete", "feedback requires completed analysis")
		return
	}
	if err := a.store.SaveFeedback(r.Context(), id, payload.Rating, payload.Comment); err != nil {
		writeError(w, http.StatusInternalServerError, "storage_error", err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"success": true})
}

func (a *API) requestNewsRefresh(w http.ResponseWriter, r *http.Request, companyID string) {
	exists, err := a.store.CompanyExists(r.Context(), companyID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "storage_error", err.Error())
		return
	}
	if !exists {
		writeError(w, http.StatusNotFound, "company_not_found", "company was not found")
		return
	}
	if err := a.store.RequestNewsRefresh(r.Context(), companyID); err != nil {
		writeError(w, http.StatusServiceUnavailable, "refresh_unavailable", err.Error())
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"success": true, "status": "queued"})
}

func (a *API) qualityHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "method_not_allowed", "GET is required")
		return
	}
	metrics, err := a.store.QualityMetrics(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "storage_error", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "metrics": metrics})
}
