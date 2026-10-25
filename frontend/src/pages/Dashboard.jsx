import Header from '../components/Header.jsx';
import BalanceCard from '../components/BalanceCard.jsx';
import AccountCard from '../components/AccountCard.jsx';
import NewsItem from '../components/NewsItem.jsx';
import TaskCard from '../components/TaskCard.jsx';
import { news } from '../data/mockNews.js';

const accounts = [
  { amount: '800 872,50 ₽', type: 'Расчётный ···3887', color: 'red' },
  { amount: '6 450 000,50 ₽', type: 'Расчётный ···3091', color: 'black' },
];

export default function Dashboard({ onOpenChat }) {
  return (
    <div className="dashboard">
      <Header />

      <div className="balance-row single">
        <BalanceCard
          label="Доступный остаток"
          value="10 500 872,50 ₽"
          sub="на 3 рублёвых счетах"
        />
      </div>

      <section className="section">
        <div className="section-header">
          <h2 className="section-title">Счета и карты</h2>
          <a className="section-link">Все &gt;</a>
        </div>
        {accounts.map((acc, i) => (
          <AccountCard key={i} {...acc} />
        ))}
      </section>

      <section className="section">
        <div className="section-header">
          <h2 className="section-title">Что говорят в новостях</h2>
        </div>
        {news.map((item) => (
          <NewsItem key={item.id} news={item} onClick={onOpenChat} />
        ))}
      </section>

      <div className="tasks-block">
        <h2 className="tasks-block-title">Дела в работе</h2>
        <TaskCard title="Подписать" sub="Платежи, ведомости" badge={1} />
      </div>

      <nav className="bottom-menu">Меню</nav>
    </div>
  );
}