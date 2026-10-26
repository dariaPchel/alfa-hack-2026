import { useState } from 'react';
import ChatMessage from '../components/ChatMessage.jsx';
import ChatInput from '../components/ChatInput.jsx';
import { getAnalysis, startAnalysis, submitFeedback } from '../api/client.js';

const suggestedPrompts = [
  'Как эта новость повлияет на мою компанию?',
  'Какие риски и возможности возникают?',
  'Какие действия стоит рассмотреть?',
];

const initialMessages = (news) => [
  { type: 'user', text: `Новость: ${news?.title || 'выбранное событие'}`, time: 'сейчас' },
  { type: 'bot', text: news?.text || 'Данные новости недоступны.', source: news?.source || 'Источник не указан', citations: news?.url ? [{ title: news.title, url: news.url }] : [], time: 'сейчас' },
];

export default function Chat({ companyId, news, onClose }) {
  const [messages, setMessages] = useState(() => initialMessages(news));
  const [input, setInput] = useState('');
  const [completedId, setCompletedId] = useState(null);
  const [pendingId, setPendingId] = useState(null);
  const [feedbackState, setFeedbackState] = useState('');

  const handleSend = async (text) => {
    if (!text.trim()) return;

    const userMsg = {
      type: 'user',
      text: text.trim(),
      time: 'сейчас',
    };

    const botMsg = {
      type: 'bot',
      text: 'Запускаю анализ в Go API…',
      source: 'Go API / Kafka worker',
      time: 'сейчас',
    };

    setMessages((prev) => [...prev, userMsg, botMsg]);
    setInput('');
    setCompletedId(null);
    setPendingId(null);
    setFeedbackState('');
    try {
      const accepted = await startAnalysis(companyId, news.id, text.trim());
      let analysis = await getAnalysis(accepted.analysis_id);
      for (let attempt = 0; !['complete', 'failed'].includes(analysis.status) && attempt < 180; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        analysis = await getAnalysis(accepted.analysis_id);
      }
      const responseText = analysis.status === 'failed'
        ? `Не удалось выполнить анализ: ${analysis.error || 'неизвестная ошибка'}`
        : analysis.status !== 'complete'
          ? 'Анализ ещё выполняется. Проверьте результат позже.'
          : [`Позиция банка: ${analysis.bank_view}`, `Анализ для компании: ${analysis.ai_analysis}`, analysis.solutions?.length ? `Что можно сделать: ${analysis.solutions.join('; ')}` : ''].filter(Boolean).join('\n\n');
      setMessages((prev) => [...prev.slice(0, -1), { type: 'bot', text: responseText || 'Анализ не содержит проверенного результата.', source: analysis.provenance || 'Go API', citations: analysis.citations || [], trace: analysis.trace || [], time: 'сейчас' }]);
      if (analysis.status === 'complete') setCompletedId(accepted.analysis_id);
      if (!['complete', 'failed'].includes(analysis.status)) setPendingId(accepted.analysis_id);
    } catch (requestError) {
      setMessages((prev) => [...prev.slice(0, -1), { type: 'bot', text: `Не удалось выполнить анализ: ${requestError.message}`, source: 'Ошибка API', time: 'сейчас' }]);
    }
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

      {pendingId && (
        <button className="check-analysis" onClick={async () => {
          try {
            const analysis = await getAnalysis(pendingId);
            if (['complete', 'failed'].includes(analysis.status)) {
              const resultText = analysis.status === 'failed'
                ? `Не удалось выполнить анализ: ${analysis.error || 'неизвестная ошибка'}`
                : [`Позиция банка: ${analysis.bank_view}`, `Анализ для компании: ${analysis.ai_analysis}`,
                  analysis.solutions?.length ? `Что можно сделать: ${analysis.solutions.join('; ')}` : ''].filter(Boolean).join('\n\n');
              setMessages((prev) => [...prev.slice(0, -1), {
                type: 'bot', text: resultText, source: analysis.provenance || 'Go API',
                citations: analysis.citations || [], trace: analysis.trace || [], time: 'сейчас',
              }]);
              if (analysis.status === 'complete') setCompletedId(pendingId);
              setPendingId(null);
            }
          } catch (error) {
            setFeedbackState(`Не удалось проверить задачу: ${error.message}`);
          }
        }}>Проверить результат задачи</button>
      )}
      {completedId && (
        <div className="analysis-feedback">
          {feedbackState || 'Этот анализ был полезен?'}
          {!feedbackState && ['useful', 'not_useful'].map((rating) => (
            <button key={rating} onClick={async () => {
              try {
                await submitFeedback(completedId, rating);
                setFeedbackState('Спасибо, оценка сохранена.');
              } catch (error) {
                setFeedbackState(`Не удалось сохранить оценку: ${error.message}`);
              }
            }}>{rating === 'useful' ? 'Да' : 'Нет'}</button>
          ))}
        </div>
      )}
      <ChatInput value={input} onChange={setInput} onSend={handleSend} />
    </div>
  );
}
