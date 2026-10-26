import Header from '../components/Header.jsx';
import NewsItem from '../components/NewsItem.jsx';

const rubles = (value) => Number.isFinite(Number(value)) && Number(value) > 0
  ? `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(Number(value))} ₽`
  : 'Нет данных';

const periodLabel = { '24h': '24 часа', '7d': '7 дней', '90d': '90 дней' };

export default function Dashboard({ companies, selectedCompany, demoCompany, news, newsWindow, refresh, updatedAt, onRefresh, onCompanyChange, onCompanySearch, onOpenChat }) {
  const company = selectedCompany;
  const isDemo = company?.datasetKind === 'demo';
  const isAnonymized = company?.datasetKind === 'anonymized';
  const refreshError = refresh?.error?.includes('SERPER_API_KEY')
    ? 'Ключ сервиса новостей пока не добавлен.'
    : refresh?.error;
  const hasPayments = Number(company?.paymentCount) > 0;

  return (
    <div className="dashboard">
      <Header companies={companies} selected={company} onSelect={onCompanyChange} onSearch={onCompanySearch} />

      <section className="profile-hero" aria-label="Профиль компании">
        <div className="profile-hero-top">
          <span className="profile-eyebrow">Профиль компании</span>
          <span className={`data-badge ${isDemo ? 'demo' : ''}`}>{isDemo ? 'Демо' : isAnonymized ? 'Данные ТЗ' : 'Учебные данные'}</span>
        </div>
        <h1>{company?.name || 'Выберите компанию'}</h1>
        <p className="profile-detail">{[company?.industry, company?.region].filter(Boolean).join(' · ') || 'Отрасль и регион не указаны'}</p>
        <div className="profile-metrics">
          <div><span>Выручка</span><strong>{company?.revenueAmount ? rubles(company.revenueAmount) : company?.revenue || 'Нет данных'}</strong></div>
          <div><span>Сотрудники</span><strong>{company?.employees || 'Нет данных'}</strong></div>
        </div>
        <p className="profile-caption">{isDemo ? 'Пример для проверки интерфейса: новости и ответ шаблонные.' : isAnonymized ? 'Обезличенный профиль из набора ТЗ. Это не банковские остатки.' : 'Учебный профиль. Это не реальные банковские данные.'}</p>
      </section>

      <section className="section company-facts">
        <div className="section-header"><h2 className="section-title">Данные компании</h2></div>
        <div className="fact-card">
          <span className="fact-icon">₽</span>
          <div className="fact-copy"><strong>{isDemo ? 'Банковские продукты' : 'Платежи в наборе ТЗ'}</strong><small>{isDemo ? 'Указаны в демонстрационном профиле' : 'Агрегированные операции, не остаток на счёте'}</small></div>
          <span className="fact-value">{isDemo ? (company?.products?.length || 0) : (hasPayments ? new Intl.NumberFormat('ru-RU').format(company.paymentCount) : '—')}</span>
        </div>
        <div className="fact-card">
          <span className="fact-icon secondary">↗</span>
          <div className="fact-copy"><strong>{isDemo ? 'Кредитная экспозиция' : 'Входящие платежи'}</strong><small>{isDemo ? 'Из демонстрационного профиля' : 'Сумма по обезличенному набору'}</small></div>
          <span className="fact-value">{isDemo ? (company?.keyRateExposure ? 'Есть' : '—') : rubles(company?.inboundPaymentAmount)}</span>
        </div>
        {Boolean(company?.products?.length) && <p className="products-note">Продукты: {company.products.join(', ')}</p>}
      </section>

      <section className="section news-section">
        <div className="section-header news-heading">
          <h2 className="section-title">{isDemo ? 'Что говорят в новостях' : 'Новости отрасли'}</h2>
          <button className="news-refresh-button" type="button" onClick={onRefresh} disabled={['queued', 'running'].includes(refresh?.status)}>Обновить</button>
        </div>
        <p className="news-context">{isDemo ? 'Демонстрационные события' : 'Подборка по отрасли, без поиска по обезличенному ID'} · за {periodLabel[newsWindow] || newsWindow}{updatedAt ? ` · получено ${new Date(updatedAt).toLocaleString('ru-RU')}` : ''}</p>
        {refresh?.status === 'failed' && <p className="news-alert">Обновление не удалось: {refreshError}</p>}
        {['queued', 'running'].includes(refresh?.status) && <p className="news-alert">Ищем новости…</p>}
        {refresh?.status === 'pending' && <p className="news-alert">Поиск продолжается. Проверьте результат позже.</p>}
        {news.length === 0 ? (
          <div className="news-empty">
            <span className="news-empty-icon" aria-hidden="true">✦</span>
            <strong>Пока нет новостей для этой компании</strong>
            <p>В ленту попадают только датированные публикации со ссылкой на источник. Нажмите «Обновить» или выберите компанию с доступными новостями.</p>
            {demoCompany && !isDemo && <button type="button" onClick={() => onCompanyChange(demoCompany)}>Открыть демопример</button>}
          </div>
        ) : news.map((item) => <NewsItem key={item.id} news={item} onClick={onOpenChat} />)}
      </section>

      <div className="tasks-block">
        <h2 className="tasks-block-title">Анализ событий</h2>
        <p className="tasks-explainer">{news.length ? 'Выберите новость выше, чтобы задать вопрос и увидеть анализ.' : 'Когда появятся новости, здесь можно будет перейти к анализу выбранного события.'}</p>
      </div>
    </div>
  );
}
