export default function ChatMessage({ message }) {
  const isUser = message.type === 'user';

  const paragraphs = message.text
    ? message.text.split('\n\n').filter((p) => p.trim())
    : [];

  return (
    <div className={`message-wrapper ${isUser ? 'user' : 'bot'}`}>
      <div className={`message-bubble ${isUser ? 'user' : 'bot'}`}>
        {paragraphs.length > 0 ? (
          paragraphs.map((paragraph, i) => (
            <p key={i} className={`message-paragraph ${isUser ? 'user-text' : ''}`}>
              {isUser ? paragraph : formatText(paragraph)}
            </p>
          ))
        ) : (
          <p className="message-paragraph empty-answer">(Ответ)</p>
        )}
      </div>

      <div className="message-meta-row">
        <span className="message-time">{message.time}</span>
        {message.source && (
          <span className="message-source"> · {message.source}</span>
        )}
      </div>
    </div>
  );
}

function formatText(text) {
  const parts = text.split(/(\d+[,.]?\d*%?)/g);

  return parts.map((part, i) => {
    const boldPhrases = [
      'ключевая ставка',
      'период быстрого удешевления',
      'стоимость обслуживания',
      'планировать новые заимствования',
    ];

    const isBold = boldPhrases.some((phrase) =>
      part.toLowerCase().includes(phrase)
    );

    const isPercentage = /^\d+[,.]?\d*%$/.test(part);
    const isDecimalNumber = /^\d+[,.]\d{2}$/.test(part); // типа 14,00
    const isNumber = (isPercentage || isDecimalNumber) && !/^\d{4}$/.test(part);

    if (isNumber) {
      return (
        <span key={i} className="message-highlight">
          {part}
        </span>
      );
    }

    if (isBold) {
      return (
        <strong key={i} className="message-bold">
          {part}
        </strong>
      );
    }

    return part;
  });
}