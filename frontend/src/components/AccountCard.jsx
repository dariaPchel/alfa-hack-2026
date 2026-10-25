export default function AccountCard({ amount, type, color }) {
  const cleanAmount = amount.replace('₽', '').trim();
  const parts = cleanAmount.split(',');
  const mainPart = parts[0];
  const decimalPart = parts.length > 1 ? ',' + parts[1] : '';

  return (
    <div className="account-card">
      <div className="account-ruble-icon">₽</div>
      <div className="account-info">
        <div className="account-amount">
          <span className="account-amount-main">{mainPart}</span>
          <span className="account-amount-decimal">{decimalPart} ₽</span>
        </div>
        <div className="account-type">{type}</div>
      </div>
      <img
        src={color === 'red' ? '/redcard.png' : '/blackcard.png'}
        alt="Карта"
        className="account-card-img"
      />
    </div>
  );
}