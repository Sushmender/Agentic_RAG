/**
 * frontend/src/pages/QueryPage.jsx
 * Query input and results page.
 * Day 0: basic scaffold.
 * Day 5: full pipeline implementation.
 */

import './QueryPage.css';

export default function QueryPage() {
  return (
    <div className="page query-page">
      <div className="page-header">
        <h1 className="page-title">💬 Ask a Question</h1>
        <p className="page-subtitle">
          Query your documents using multimodal RAG — text, tables, figures, and images.
        </p>
      </div>

      {/* Query form — Day 4/5 implementation */}
      <div className="query-form">
        <textarea
          className="query-input"
          placeholder="Ask anything about your documents... e.g. 'What was the revenue in Q3?' or 'Show me the sales table'"
          rows={3}
          disabled
        />
        <button className="query-btn" disabled>
          Ask Question
        </button>
        <div className="query-coming-soon">
          Query pipeline available from Day 5.
        </div>
      </div>

      {/* Results area */}
      <div className="query-results">
        <div className="empty-state">
          <span className="empty-icon">💡</span>
          <p>Ask a question to get grounded answers with source citations.</p>
        </div>
      </div>
    </div>
  );
}
