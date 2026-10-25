import { useState } from 'react';
import ChatMessage from '../components/ChatMessage.jsx';
import ChatInput from '../components/ChatInput.jsx';

const suggestedPrompts = [
  'Как ставка 21% влияет на мои кредиты?',
  'Как ставка бьёт по моей отрасли?',
  'Как ставка влияет на мою оборотку?',
];

const initialMessages = [
  {
    type: 'user',
    text: 'Новость от ЦБ, про решение сохранять ключевую ставку в 14,00% и первую паузу после серии снижений',
    time: '19:25',
  },
  {
    type: 'bot',
    text: `ЦБ 11 сентября 2026 года сохранил ключевую ставку на уровне 14,00% годовых. Это первая пауза в цикле смягчения после серии последовательных снижений.

Для вашего бизнеса это означает: период быстрого удешевления финансирования приостановлен.

Ключевая ставка осталась на уровне 14% — деньги не дешевеют дальше, а значит, стоимость обслуживания ваших кредитных продуктов в ближайшей перспективе не снизится.

Если часть инвестиций финансируется за счёт заёмных средств, планировать новые заимствования или рефинансирование стоит исходя из того, что ставка пока «замерла» на текущем уровне.`,
    source: 'Центральный Банк РФ',
    time: '19:26',
  },
  {
    type: 'user',
    text: 'Как это влияет на лизинг?',
    time: '19:26',
  },
  {
    type: 'bot',
    text: '(Ответ)',
    source: 'Центральный банк РФ, РИА новости',
    time: '19:26',
  },
];

export default function Chat({ news, onClose }) {
  const [messages, setMessages] = useState(initialMessages);
  const [input, setInput] = useState('');

  const handleSend = (text) => {
    if (!text.trim()) return;

    const userMsg = {
      type: 'user',
      text: text.trim(),
      time: '19:27',
    };

    const botMsg = {
      type: 'bot',
      text: 'Анализирую данные...',
      source: 'Альфа-Банк Аналитика',
      time: '19:27',
    };

    setMessages((prev) => [...prev, userMsg, botMsg]);
    setInput('');
  };

  return (
    <div className="chat-screen">
      <div className="chat-header">
        <button className="chat-close" onClick={onClose}>✕</button>
        <img
          src="/logo-alfred.png"
          alt="ALFRED"
          className="chat-header-logo"
        />
      </div>

      <div className="chat-messages">
        {messages.map((msg, i) => (
          <ChatMessage key={i} message={msg} />
        ))}

        {/* Подсказки — внутри chat-messages, сразу после последнего сообщения */}
        <div className="suggested-prompts">
          {suggestedPrompts.map((prompt, i) => (
            <button
              key={i}
              className="prompt-btn"
              onClick={() => handleSend(prompt)}
            >
              {prompt}
            </button>
          ))}
        </div>
      </div>

      <ChatInput value={input} onChange={setInput} onSend={handleSend} />
    </div>
  );
}