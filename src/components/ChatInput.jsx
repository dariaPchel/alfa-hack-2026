export default function ChatInput({ value, onChange, onSend }) {
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && value.trim()) {
      onSend(value);
    }
  };

  return (
    <div className="chat-input-wrapper">
      <div className="chat-input-box">
        <img
          src="/skrepka.png"
          alt="Прикрепить"
          className="chat-input-skrepka"
        />
        <input
          className="chat-input"
          placeholder="Уточнить детали...."
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button
          className="chat-input-send"
          onClick={() => value.trim() && onSend(value)}
        >
          <img
            src="/pointer%20up.png"
            alt="Отправить"
            className="chat-input-send-icon"
          />
        </button>
      </div>
    </div>
  );
}