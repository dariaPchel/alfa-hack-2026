import { useState } from 'react';

export default function Header({ companies, selected, onSelect, onSearch }) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');

  return (
    <header className="app-header">
      <img src="/logo.png" alt="Альфа-Банк" className="company-logo-img" />
      <div style={{ position: 'relative', flex: 1, minWidth: 0 }}>
        <button className="company-selector" type="button" aria-expanded={isOpen} aria-label="Выбрать компанию" onClick={() => setIsOpen(!isOpen)}>
          <span className="company-selector-name">{selected?.name || 'Компания'}</span>
          <img src="/pointer%20down.png" alt="" className={`selector-arrow ${isOpen ? 'rotated' : ''}`} />
        </button>
        {isOpen && (
          <div className="dropdown-menu">
            <form className="company-search" onSubmit={(event) => { event.preventDefault(); onSearch(query); }}>
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="ID, отрасль или регион" aria-label="Поиск компании" />
              <button type="submit">Найти</button>
            </form>
            {companies.length === 0 && <p className="dropdown-empty">Компании не найдены</p>}
            {companies.map((company) => (
              <button key={company.id} type="button" className="dropdown-item" onClick={() => { onSelect(company); setIsOpen(false); }}>
                {company.name}{company.datasetKind === 'demo' ? ' · демо' : ''}
              </button>
            ))}
          </div>
        )}
      </div>
    </header>
  );
}
