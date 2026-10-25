export default function TaskCard({ title, sub, badge }) {
  return (
    <div className="task-card">
      <div className="task-icon">
        <img src="/pen.png" alt="Подписать" className="task-icon-img" />
      </div>
      <div className="task-info">
        <div className="task-title">{title}</div>
        <div className="task-sub">{sub}</div>
      </div>
      {badge && <div className="task-badge">{badge}</div>}
    </div>
  );
}