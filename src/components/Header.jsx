import { useState } from 'react';
import { companies } from '../data/mockCompanies.js';

export default function Header() {
  const [isOpen, setIsOpen] = useState(false);
  const [selected, setSelected] = useState(companies[0]);

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
          <span className="company-selector-name">{selected.name}</span>
          <img
            src="/pointer%20down.png"
            alt="dropdown"
            className={`selector-arrow ${isOpen ? 'rotated' : ''}`}
          />
        </button>

        {isOpen && (
          <div className="dropdown-menu">
            {companies.map((company) => (
              <div
                key={company.id}
                className="dropdown-item"
                onClick={() => {
                  setSelected(company);
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