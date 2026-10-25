export const formatMoney = (amount) => {
  return amount.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + ' ₽';
};

export const formatNumber = (num) => {
  return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
};

export const formatTime = (date) => {
  return date.toLocaleTimeString('ru-RU', {
    hour: '2-digit',
    minute: '2-digit',
  });
};