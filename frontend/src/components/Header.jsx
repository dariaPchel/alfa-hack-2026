import { useState } from 'react';

export default function Header({ companies, selected, onSelect, onSearch }) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');

  return (
    <header className="app-header">
      <img
        src="/logo.png"
        alt="Альфа-Банк"
        className="company-logo-img"
      />

      <div style={{ position: 'relative', flex: 1 }}>
        <button
          className="company-selector"
          onClick={() => setIsOpen(!isOpen)}
        >
          <span className="company-selector-name">{selected?.name || 'Компания'}</span>
          <img
            src="/pointer%20down.png"
            alt="dropdown"
            className={`selector-arrow ${isOpen ? 'rotated' : ''}`}
          />
        </button>

        {isOpen && (
          <div className="dropdown-menu">
            <form className="company-search" onSubmit={(event) => { event.preventDefault(); onSearch(query); }}>
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="ID, отрасль или регион" aria-label="Поиск компании" />
              <button type="submit">Найти</button>
            </form>
            {companies.map((company) => (
              <div
                key={company.id}
                className="dropdown-item"
                onClick={() => {
                  onSelect(company);
                  setIsOpen(false);
                }}
              >
                {company.name}
              </div>
            ))}
          </div>
        )}
      </div>
    </header>
  );
}
