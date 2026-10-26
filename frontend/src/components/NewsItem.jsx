export default function NewsItem({ news, onClick }) {
  return (
    <button type="button" className="news-item" onClick={() => onClick(news)}>
      {news.icon === 'cb'
        ? <img src="/centralbank.png" alt="Банк России" className="news-icon-img" />
        : <span className="news-generic-icon" aria-hidden="true">Н</span>}
      <div className="news-text">{news.title || news.text}<small className="news-source-name">{news.source}</small></div>
      <div className="news-time">{news.time}</div>
    </button>
  );
}