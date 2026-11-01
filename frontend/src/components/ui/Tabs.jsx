/**
 * src/components/ui/Tabs.jsx
 * Segmented control–style tabs
 */
import './Tabs.css';

export function Tabs({ tabs, active, onChange, className = '' }) {
  return (
    <div className={`tabs ${className}`} role="tablist">
      {tabs.map(tab => (
        <button
          key={tab.value}
          role="tab"
          aria-selected={active === tab.value}
          className={`tabs__tab ${active === tab.value ? 'tabs__tab--active' : ''}`}
          onClick={() => onChange(tab.value)}
        >
          {tab.icon && <span className="tabs__icon" aria-hidden="true">{tab.icon}</span>}
          {tab.label}
          {tab.count != null && (
            <span className="tabs__count">{tab.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}

export default Tabs;
