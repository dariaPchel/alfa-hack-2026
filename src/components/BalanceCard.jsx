export default function BalanceCard({ label, value, sub }) {
  // Убираем символ ₽ из value если он там есть, добавим сами
  const cleanValue = value.replace('₽', '').trim();
  const parts = cleanValue.split(',');
  const mainPart = parts[0]; // "10 500 872"
  const decimalPart = parts.length > 1 ? ',' + parts[1] : ''; // ",50"

  return (
    <div className="balance-card">
      <div className="balance-label">{label}</div>
      <div className="balance-value-wrapper">
        <div className="balance-value">
          <span className="balance-value-main">{mainPart}</span>
          <span className="balance-value-decimal">{decimalPart} ₽</span>
        </div>
        <img
          src="/pointer.png"
          alt=">"
          className="balance-pointer"
        />
      </div>
      {sub && <div className="balance-sub">{sub}</div>}
    </div>
  );
}