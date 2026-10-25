(() => {
  const $ = (selector) => document.querySelector(selector);
  const state = { companies: [], windows: {}, activeWindow: "90d", selectedEvent: null, busy: false, loadedCompanyId: null };
  const select = $("#company-select");
  const escText = (value) => String(value ?? "—");
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined && text !== null) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const companyId = () => select.value;

  async function api(url, options = {}) {
    const response = await fetch(url, { headers: { "Content-Type": "application/json" }, ...options });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.success === false) throw new Error(data.message || data.error_code || "Ошибка API");
    return data;
  }

  function renderCompanies() {
    state.companies.forEach((company) => {
      const option = document.createElement("option");
      option.value = company.synthetic_id;
      option.textContent = `${company.synthetic_id} · ${company.mainokved_name || company.mainokved_code || "отрасль не указана"}`;
      select.append(option);
    });
  }

  function renderSummary(company) {
    const summary = $("#company-summary");
    summary.replaceChildren();
    if (!company) return;
    const peers = company.peer_basis || [];
    const gaps = company.source_metadata?.missing_optional_fields || [];
    const items = [
      ["\u041e\u0441\u043d\u043e\u0432\u043d\u043e\u0439 \u041e\u041a\u0412\u042d\u0414", company.mainokved_name || company.mainokved_code],
      ["\u0424\u043e\u0440\u043c\u0430 \u0441\u043e\u0431\u0441\u0442\u0432\u0435\u043d\u043d\u043e\u0441\u0442\u0438", company.org_type || company.okfs_name],
      ["\u0420\u0435\u0433\u0438\u043e\u043d", company.region || company.city],
      ["\u0420\u0430\u0437\u043c\u0435\u0440", company.revenue_company || company.amount_workers_fns_gradation],
      ["\u0410\u043d\u0430\u043b\u043e\u0433\u0438", peers.length ? `${peers.length} \u00b7 \u0441\u0445\u043e\u0434\u0441\u0442\u0432\u043e \u043b\u0438\u0434\u0435\u0440\u0430 ${Math.round((peers[0].similarity_score || 0) * 100)}%` : "\u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u044b"],
      ["\u041f\u0440\u043e\u0431\u0435\u043b\u044b \u0434\u0430\u043d\u043d\u044b\u0445", gaps.length ? `${gaps.length} \u043f\u043e\u043b\u0435\u0439 \u043d\u0435 \u043f\u0440\u0435\u0434\u043e\u0441\u0442\u0430\u0432\u043b\u0435\u043d\u043e` : "\u043d\u0435 \u0432\u044b\u044f\u0432\u043b\u0435\u043d\u044b"]
    ];
    items.forEach(([label, value]) => {
      const card = node("div", undefined, "summary-item");
      card.append(node("span", label), node("strong", escText(value)));
      summary.append(card);
    });
    $("#data-provenance").textContent = "Источник: обезличенная запись хакатона. Rusprofile-компании используются только как аналоги.";
  }

  function renderFeed() {
    const list = $("#event-list");
    const window = state.windows[state.activeWindow];
    list.replaceChildren();
    $("#feed-updated").textContent = window?.updated_at ? `Обновлено ${new Date(window.updated_at).toLocaleString("ru-RU")} · ${window.actual_count} новостей` : "Окно ещё не обновлялось";
    const warning = $("#feed-warning");
    const warnings = window?.warnings || [];
    warning.textContent = warnings.join(" · ");
    warning.classList.toggle("hidden", warnings.length === 0);
    if (!window?.events?.length) {
      list.append(node("div", "В этом временном окне нет новостей с датой публикации.", "empty"));
      return;
    }
    window.events.forEach((event) => {
      const card = node("article", undefined, "event-card");
      card.tabIndex = 0;
      const meta = node("div", undefined, "event-meta");
      meta.append(node("span", event.publisher || "Источник"), node("span", event.published_at ? new Date(event.published_at).toLocaleDateString("ru-RU") : "Дата не определена"), node("span", "Новость", "tag"));
      card.append(meta, node("h3", event.title), node("p", event.snippet || "Откройте новость для анализа."));
      card.addEventListener("click", () => openEvent(event));
      card.addEventListener("keydown", (keyEvent) => { if (keyEvent.key === "Enter") openEvent(event); });
      list.append(card);
    });
  }

  async function loadCompany() {
    const id = companyId();
    if (id !== state.loadedCompanyId) state.windows = {};
    state.selectedEvent = null;
    $("#detail-panel").classList.add("hidden");
    renderSummary(state.companies.find((item) => item.synthetic_id === id));
    if (!id) { renderFeed(); return; }
    $("#service-status").textContent = "Загружаем новости";
    try {
      const result = await api(`/api/companies/${encodeURIComponent(id)}/news`);
      state.windows = result.windows || {};
      state.loadedCompanyId = id;
      renderSummary(result.profile || state.companies.find((item) => item.synthetic_id === id));
      if (result.warnings?.length) {
        $("#feed-warning").textContent = result.warnings.join(" · ");
        $("#feed-warning").classList.remove("hidden");
      }
      $("#service-status").textContent = "Данные загружены";
    } catch (error) {
      $("#service-status").textContent = "Новости недоступны";
      $("#feed-warning").textContent = error.message;
      $("#feed-warning").classList.remove("hidden");
    }
    renderFeed();
  }

  function renderTextSection(title, content) {
    const section = node("section", undefined, "section-card");
    section.append(node("h3", title));
    if (Array.isArray(content)) {
      const list = node("ul"); content.forEach((item) => list.append(node("li", typeof item === "string" ? item : JSON.stringify(item)))); section.append(list);
    } else section.append(node("p", typeof content === "string" ? content : JSON.stringify(content ?? "Нет данных")));
    return section;
  }

  async function openEvent(event) {
    state.selectedEvent = event;
    $("#detail-panel").classList.remove("hidden");
    $("#detail-title").textContent = event.title;
    const content = $("#detail-content"); content.replaceChildren();
    const link = node("a", "Открыть источник", "source-link"); link.href = event.url; link.target = "_blank"; link.rel = "noopener noreferrer";
    const header = node("div", undefined, "section-card"); header.append(link, node("p", event.snippet)); content.append(header);
    try {
      const result = await api(`/api/companies/${encodeURIComponent(companyId())}/news/${encodeURIComponent(event.event_id)}`);
      if (result.analysis) renderAnalysis(result.analysis, content);
      else content.append(renderTextSection("Анализ", "Для этой новости анализ ещё не сформирован."));
    } catch (error) { content.append(renderTextSection("Состояние", error.message)); }
    $("#detail-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderAnalysis(item, root) {
    const label = node("span", item.qualitative_impact || "mixed", `impact-label ${item.qualitative_impact === "opportunity" ? "opportunity" : ""}`);
    const summary = node("section", undefined, "section-card");
    summary.append(label, node("p", item.why_relevant), node("p", `Горизонт: ${item.horizon || "—"} · Уверенность: ${Math.round((item.confidence || 0) * 100)}%`));
    root.append(summary);
    const kpis = node("section", undefined, "section-card"); kpis.append(node("h3", "Сценарная оценка показателей"));
    const row = node("div", undefined, "kpi-row");
    (item.event_kpi_changes || []).forEach((kpi) => {
      const box = node("div", undefined, "kpi"); box.append(node("strong", `${kpi.metric}: ${kpi.change_pct_min}% … ${kpi.change_pct_max}%`), node("span", `${kpi.period} · ${kpi.baseline_basis}`)); row.append(box);
    }); kpis.append(row); root.append(kpis);
    root.append(renderTextSection("Позиция аналитики Альфа-Банка", item.bank_view?.summary));
    root.append(renderTextSection("Применённая методика", (item.risk_method_used || []).map((method) => method.method)));
    root.append(renderTextSection("Анализ события", item.ai_analysis));
    (item.solutions || []).forEach((solution) => {
      const card = node("section", undefined, "section-card"); card.append(node("h3", solution.title), node("p", `${solution.verification_status} · ${solution.objective}`));
      const steps = node("ol"); (solution.steps || []).forEach((step) => steps.append(node("li", `${step.action} — ${step.owner}, до ${step.due_in_days} дн. Критерии: ${(step.completion_criteria || []).join(", ")}`)));
      card.append(steps, node("p", `Ресурсы: ${solution.resources_and_cost || "—"}`), node("p", `Резервный план: ${solution.fallback_plan || "—"}`));
      (solution.expected_kpi_changes || []).forEach((kpi) => card.append(node("p", `${kpi.metric}: ${kpi.change_pct_min}% … ${kpi.change_pct_max}% (${kpi.period})`)));
      root.append(card);
    });
    root.append(renderTextSection("Источники и допущения", (item.citations || []).map((citation) => `${citation.title} · ${citation.url || citation.source_id}`)));
  }

  async function analyzeSelected() {
    if (!state.selectedEvent || state.busy) return;
    state.busy = true; const button = $("#analyze-button"); button.disabled = true; button.textContent = "Формируем план…";
    try {
      const result = await api(`/api/companies/${encodeURIComponent(companyId())}/analyze`, {
        method: "POST", body: JSON.stringify({ event_ids: [state.selectedEvent.event_id] }),
      });
      const event = (result.events || []).find((item) => item.event_id === state.selectedEvent.event_id);
      if (event) { const content = $("#detail-content"); content.replaceChildren(); renderAnalysis(event, content); }
      else $("#detail-content").append(renderTextSection("Результат", (result.warnings || []).join(" · ") || "Анализ не вернул готовый результат."));
    } catch (error) {
      $("#detail-content").append(renderTextSection("Не удалось сформировать анализ", error.message));
    } finally { state.busy = false; button.disabled = false; button.textContent = "Сформировать анализ"; }
  }

  async function init() {
    try { const data = await api("/api/companies"); state.companies = data.companies || []; renderCompanies(); $("#service-status").textContent = `${data.count || 0} компаний`; }
    catch (error) { $("#service-status").textContent = error.message; }
  }
  select.addEventListener("change", loadCompany);
  $("#refresh-button").addEventListener("click", loadCompany);
  $("#analyze-button").addEventListener("click", analyzeSelected);
  document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("active", item === tab));
    state.activeWindow = tab.dataset.window; renderFeed();
  }));
  init();
})();
