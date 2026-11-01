/**
 * NotFoundPage.jsx — custom 404 page in the app's design language
 */
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Home, ArrowLeft } from 'lucide-react';
import './NotFoundPage.css';

export default function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <div className="not-found">
      <motion.div
        className="not-found__content"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
      >
        <div className="not-found__code mono">404</div>
        <h1 className="not-found__title">Page not found</h1>
        <p className="not-found__sub">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <div className="not-found__actions">
          <button
            className="btn-nf btn-nf--primary"
            onClick={() => navigate('/')}
            id="not-found-home-btn"
          >
            <Home size={15} /> Go to Documents
          </button>
          <button
            className="btn-nf btn-nf--secondary"
            onClick={() => navigate(-1)}
            id="not-found-back-btn"
          >
            <ArrowLeft size={15} /> Go back
          </button>
        </div>
      </motion.div>

      {/* Decorative grid lines */}
      <div className="not-found__grid" aria-hidden="true">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="not-found__grid-line" />
        ))}
      </div>
    </div>
  );
}
