export default function ChatInput({ value, onChange, onSend }) {
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && value.trim()) {
      onSend(value);
    }
  };

  return (
    <div className="chat-input-wrapper">
      <div className="chat-input-box">

        <input
          className="chat-input"
          placeholder="Задайте вопрос о новости"
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