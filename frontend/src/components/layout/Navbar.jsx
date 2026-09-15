/**
 * frontend/src/components/layout/Navbar.jsx
 * Top navigation bar with links and logout.
 */

import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import './Navbar.css';

export default function Navbar() {
  const { user, logout } = useAuth();
  const location = useLocation();

  return (
    <nav className="navbar">
      <div className="navbar-brand">
        <span className="navbar-logo">⚡</span>
        <span className="navbar-title">Multimodal RAG</span>
      </div>

      <div className="navbar-links">
        <Link
          to="/"
          className={`navbar-link ${location.pathname === '/' ? 'active' : ''}`}
        >
          📁 Documents
        </Link>
        <Link
          to="/query"
          className={`navbar-link ${location.pathname === '/query' ? 'active' : ''}`}
        >
          💬 Query
        </Link>
      </div>

      <div className="navbar-user">
        <span className="navbar-username">👤 {user?.username}</span>
        <button className="navbar-logout" onClick={logout}>
          Logout
        </button>
      </div>
    </nav>
  );
}
