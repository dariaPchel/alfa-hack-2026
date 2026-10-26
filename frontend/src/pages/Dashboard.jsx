import Header from '../components/Header.jsx';
import NewsItem from '../components/NewsItem.jsx';

export default function Dashboard({ companies, selectedCompany, news, newsWindow, refresh, updatedAt, onRefresh, onCompanyChange, onCompanySearch, onOpenChat }) {
  return (
    <div className="dashboard">
      <Header companies={companies} selected={selectedCompany} onSelect={onCompanyChange} onSearch={onCompanySearch} />

      <section className="section">
        <div className="section-header">
          <h2 className="section-title">Новостная аналитика</h2>
          <span className="news-period">за {newsWindow}</span>
          <button className="news-refresh-button" type="button" onClick={onRefresh} disabled={['queued','running'].includes(refresh?.status)}>{refresh?.status === 'pending' ? 'Проверить' : 'Обновить'}</button>
        </div>
        {updatedAt && <p className="news-freshness">Получено: {new Date(updatedAt).toLocaleString('ru-RU')}</p>}
        {refresh?.status === 'failed' && <p>Обновление не удалось: {refresh.error}</p>}
        {['queued','running'].includes(refresh?.status) && <p>Ищем новости…</p>}
        {refresh?.status === 'pending' && <p>Обновление ещё выполняется. Проверьте результат позже.</p>}
        {news.length === 0 && <p>Пока нет датированных новостей со ссылкой на источник. Проверьте подключение поставщика новостей.</p>}
        {news.map((item) => (
          <NewsItem key={item.id} news={item} onClick={onOpenChat} />
        ))}
      </section>

    </div>
  );
}
