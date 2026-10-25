import { useState } from 'react';
import Dashboard from './pages/Dashboard.jsx';
import Chat from './pages/Chat.jsx';

export default function App() {
  const [screen, setScreen] = useState('dashboard');
  const [selectedNews, setSelectedNews] = useState(null);

  const openChat = (news) => {
    setSelectedNews(news);
    setScreen('chat');
  };

  const closeChat = () => {
    setScreen('dashboard');
    setSelectedNews(null);
  };

  return (
    <>
      {screen === 'dashboard' && <Dashboard onOpenChat={openChat} />}
      {screen === 'chat' && <Chat news={selectedNews} onClose={closeChat} />}
    </>
  );
}