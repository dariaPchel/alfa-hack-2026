export default function NewsItem({ news, onClick }) {
  const iconSrc =
    news.icon === 'cb' ? '/centralbank.png' : '/ria%20news.png';

  return (
    <div className="news-item" onClick={() => onClick(news)}>
      <img src={iconSrc} alt="icon" className="news-icon-img" />
      <div className="news-text">{news.text}</div>
      <div className="news-time">{news.time}</div>
    </div>
  );
}