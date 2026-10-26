import { useEffect, useRef, useState } from 'react';
import Dashboard from './pages/Dashboard.jsx';
import Chat from './pages/Chat.jsx';
import { getCompanies, getCompanyNews, requestNewsRefresh } from './api/client.js';

export default function App() {
  const [screen, setScreen] = useState('dashboard');
  const selectedCompanyId = useRef(null);
  const [selectedNews, setSelectedNews] = useState(null);
  const [companies, setCompanies] = useState([]);
  const [selectedCompany, setSelectedCompany] = useState(null);
  const [news, setNews] = useState([]);
  const [newsWindow, setNewsWindow] = useState('24h');
  const [refresh, setRefresh] = useState({});
  const [updatedAt, setUpdatedAt] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const loadedCompanies = await getCompanies();
        const company = loadedCompanies[0];
        const loadedNews = company ? await getCompanyNews(company.id) : { events: [], window: '24h' };
        if (!cancelled) { setCompanies(loadedCompanies); setSelectedCompany(company); selectedCompanyId.current = company?.id || null; setNews(loadedNews.events); setNewsWindow(loadedNews.window); setRefresh(loadedNews.refresh); setUpdatedAt(loadedNews.updatedAt || ''); }
      } catch (requestError) {
        if (!cancelled) { setCompanies([]); setSelectedCompany(null); setNews([]); setError(requestError.message); }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  const handleCompanySearch = async (query) => {
    try { setCompanies(await getCompanies(query)); setError(''); }
    catch (requestError) { setError(requestError.message); }
  };

  const handleCompanyChange = async (company) => {
    setSelectedCompany(company);
    selectedCompanyId.current = company.id;
    try { const result = await getCompanyNews(company.id); if (selectedCompanyId.current !== company.id) return; setNews(result.events); setNewsWindow(result.window); setRefresh(result.refresh); setUpdatedAt(result.updatedAt || ''); setError(''); }
    catch (requestError) { setNews([]); setError(requestError.message); }
  };

  const handleRefresh = async () => {
    if (!selectedCompany) return;
    const companyId = selectedCompany.id;
    try {
      if (refresh?.status !== 'pending') {
        await requestNewsRefresh(companyId);
        setRefresh({ status: 'queued' });
      }
      let finished = false;
      for (let attempt = 0; attempt < 60; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        const result = await getCompanyNews(companyId);
        if (selectedCompanyId.current !== companyId) break;
        setRefresh(result.refresh);
        if (['complete', 'failed'].includes(result.refresh?.status)) {
          setNews(result.events);
          setNewsWindow(result.window);
          setUpdatedAt(result.updatedAt || '');
          finished = true;
          break;
        }
      }
      if (!finished && selectedCompanyId.current === companyId) setRefresh({ status: 'pending' });
    } catch (requestError) { setError(requestError.message); }
  };

  const openChat = (news) => {
    setSelectedNews(news);
    setScreen('chat');
  };

  const closeChat = () => {
    setScreen('dashboard');
    setSelectedNews(null);
  };

  if (loading) return <div className="app-state">Загружаю данные компании…</div>;

  return (
    <>
      {error && <div className="api-status">Не удалось загрузить данные: {error}</div>}
      {selectedCompany?.datasetKind && <div className="api-status">{selectedCompany.datasetKind === 'demo' ? 'Демонстрационные данные и шаблонный ответ.' : 'Обезличенные данные из ТЗ.'}</div>}
      {screen === 'dashboard' && <Dashboard companies={companies} selectedCompany={selectedCompany} news={news} newsWindow={newsWindow} refresh={refresh} updatedAt={updatedAt} onRefresh={handleRefresh} onCompanyChange={handleCompanyChange} onCompanySearch={handleCompanySearch} onOpenChat={openChat} />}
      {screen === 'chat' && <Chat companyId={selectedCompany?.id} news={selectedNews} onClose={closeChat} />}
    </>
  );
}
