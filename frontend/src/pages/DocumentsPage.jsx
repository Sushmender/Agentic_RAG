/**
 * frontend/src/pages/DocumentsPage.jsx
 * Day 1+2 — Full implementation:
 *   - Drag-and-drop upload via react-dropzone
 *   - Upload progress + job status polling (2s interval)
 *   - Document list with color-coded status badges
 *   - View Details panel: chunk count, chunk types, ADE credits, parser version
 *   - Empty state, error toasts, "Query" navigation
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDropzone } from 'react-dropzone';
import { documentsAPI, jobsAPI } from '../services/api';
import './DocumentsPage.css';

// ── Status badge component ─────────────────────────────────────────────────────
function StatusBadge({ status }) {
  const labels = {
    pending: '⏳ Pending',
    processing: '⚙️ Processing',
    completed: '✅ Complete',
    failed: '❌ Failed',
  };
  return (
    <span className={`badge badge-${status}`}>
      {labels[status] || status}
    </span>
  );
}

// ── Document card ──────────────────────────────────────────────────────────────
function DocumentCard({ doc, onQuery }) {
  const [expanded, setExpanded] = useState(false);
  const sizeKB = (doc.file_size_bytes / 1024).toFixed(1);

  const docIcon =
    doc.document_type === 'pdf'  ? '📄' :
    doc.document_type === 'docx' ? '📝' :
    doc.document_type === 'pptx' ? '📊' :
    doc.document_type === 'xlsx' ? '📈' : '🖼️';

  return (
    <div className={`doc-card doc-card--${doc.status} animate-fade-in`}>
      <div className="doc-card__icon">{docIcon}</div>

      <div className="doc-card__body">
        <div className="doc-card__name">{doc.filename}</div>

        {/* ── Primary meta row ── */}
        <div className="doc-card__meta">
          <span>{doc.document_type?.toUpperCase()}</span>
          <span>·</span>
          <span>{sizeKB} KB</span>
          {doc.chunk_count > 0 && (
            <>
              <span>·</span>
              <span className="doc-card__chunks">🧩 {doc.chunk_count} chunks</span>
            </>
          )}
          {doc.parser_version && (
            <>
              <span>·</span>
              <span className="doc-card__version">{doc.parser_version}</span>
            </>
          )}
          {doc.ade_credits_used > 0 && (
            <>
              <span>·</span>
              <span className="doc-card__credits">💳 {doc.ade_credits_used.toFixed(1)} credits</span>
            </>
          )}
        </div>

        {/* ── Error message ── */}
        {doc.error_message && (
          <div className="doc-card__error">{doc.error_message}</div>
        )}

        {/* ── Processing progress bar ── */}
        {doc.status === 'processing' && (
          <div className="doc-card__progress">
            <div className="progress-bar">
              <div className="progress-bar__fill progress-bar__fill--animated" />
            </div>
          </div>
        )}

        {/* ── Expandable View Details ── */}
        {doc.status === 'completed' && (
          <div className="doc-card__details">
            <button
              className="doc-card__details-toggle"
              onClick={() => setExpanded((v) => !v)}
              aria-expanded={expanded}
            >
              {expanded ? '▲ Hide Details' : '▼ View Details'}
            </button>

            {expanded && (
              <div className="doc-card__details-panel animate-fade-in">
                <div className="details-grid">
                  <div className="details-item">
                    <span className="details-label">Filename</span>
                    <span className="details-value">{doc.filename}</span>
                  </div>
                  <div className="details-item">
                    <span className="details-label">File Type</span>
                    <span className="details-value">{doc.document_type?.toUpperCase()}</span>
                  </div>
                  <div className="details-item">
                    <span className="details-label">File Size</span>
                    <span className="details-value">{sizeKB} KB</span>
                  </div>
                  {doc.chunk_count > 0 && (
                    <div className="details-item">
                      <span className="details-label">Total Chunks</span>
                      <span className="details-value details-value--highlight">
                        🧩 {doc.chunk_count}
                      </span>
                    </div>
                  )}
                  {doc.parser_version && (
                    <div className="details-item">
                      <span className="details-label">Parser Version</span>
                      <span className="details-value details-value--code">{doc.parser_version}</span>
                    </div>
                  )}
                  {doc.ade_credits_used > 0 && (
                    <div className="details-item">
                      <span className="details-label">ADE Credits Used</span>
                      <span className="details-value details-value--credits">
                        💳 {doc.ade_credits_used.toFixed(2)}
                      </span>
                    </div>
                  )}
                  <div className="details-item">
                    <span className="details-label">Document ID</span>
                    <span className="details-value details-value--mono details-value--truncate">
                      {doc.document_id.slice(0, 16)}…
                    </span>
                  </div>
                  <div className="details-item">
                    <span className="details-label">Status</span>
                    <span className="details-value"><StatusBadge status={doc.status} /></span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="doc-card__right">
        <StatusBadge status={doc.status} />
        {doc.status === 'completed' && (
          <button
            className="doc-card__query-btn"
            onClick={() => onQuery(doc.document_id)}
          >
            Query →
          </button>
        )}
      </div>
    </div>
  );
}

// ── Toast notification ─────────────────────────────────────────────────────────
function Toast({ toasts, onDismiss }) {
  return (
    <div className="toast-container">
      {toasts.map((t) => (
        <div key={t.id} className={`toast toast--${t.type} animate-fade-in`}>
          <span>{t.message}</span>
          <button className="toast__close" onClick={() => onDismiss(t.id)}>×</button>
        </div>
      ))}
    </div>
  );
}

// ── Upload zone ────────────────────────────────────────────────────────────────
function UploadZone({ onUpload, uploading, uploadProgress }) {
  const onDrop = useCallback((acceptedFiles) => {
    if (acceptedFiles.length > 0) {
      onUpload(acceptedFiles[0]);
    }
  }, [onUpload]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    multiple: false,
    disabled: uploading,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'image/png': ['.png'],
      'image/jpeg': ['.jpg', '.jpeg'],
      'image/webp': ['.webp'],
    },
  });

  return (
    <div
      {...getRootProps()}
      className={`upload-zone ${isDragActive ? 'upload-zone--active' : ''} ${uploading ? 'upload-zone--uploading' : ''}`}
    >
      <input {...getInputProps()} id="file-upload-input" />
      <div className="upload-zone__inner">
        <div className={`upload-icon ${isDragActive ? 'animate-pulse' : ''}`}>
          {uploading ? '⏳' : isDragActive ? '📂' : '📤'}
        </div>
        {uploading ? (
          <>
            <p className="upload-label">Uploading…</p>
            <div className="upload-progress-bar">
              <div
                className="upload-progress-bar__fill"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
            <p className="upload-hint">{uploadProgress}%</p>
          </>
        ) : (
          <>
            <p className="upload-label">
              {isDragActive ? 'Drop file here' : 'Drag & drop a file, or click to browse'}
            </p>
            <p className="upload-hint">PDF · DOCX · PPTX · XLSX · PNG · JPG · WEBP (max 50 MB)</p>
            <button className="upload-btn" type="button" disabled={uploading}>
              Choose File
            </button>
          </>
        )}
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────
export default function DocumentsPage() {
  const navigate = useNavigate();
  const [documents, setDocuments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [loading, setLoading] = useState(true);
  const [toasts, setToasts] = useState([]);

  // Polling refs: map of jobId → intervalId
  const pollingRefs = useRef({});

  // ── Toast helpers ────────────────────────────────────────────────────────────
  const addToast = (message, type = 'success') => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => dismissToast(id), 5000);
  };
  const dismissToast = (id) => setToasts((prev) => prev.filter((t) => t.id !== id));

  // ── Load document list ───────────────────────────────────────────────────────
  const loadDocuments = async () => {
    try {
      const resp = await documentsAPI.list();
      setDocuments(resp.data.documents || []);
    } catch (err) {
      addToast('Failed to load documents', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDocuments();
    return () => {
      // Clear all polling on unmount
      Object.values(pollingRefs.current).forEach(clearInterval);
    };
  }, []);

  // ── Poll job status ──────────────────────────────────────────────────────────
  const startPolling = (jobId, documentId) => {
    if (pollingRefs.current[jobId]) return; // already polling

    const intervalId = setInterval(async () => {
      try {
        const jobResp = await jobsAPI.getJob(jobId);
        const job = jobResp.data;

        // Refresh doc in list
        const docResp = await documentsAPI.get(documentId);
        setDocuments((prev) =>
          prev.map((d) => (d.document_id === documentId ? docResp.data : d))
        );

        if (job.status === 'completed') {
          clearInterval(pollingRefs.current[jobId]);
          delete pollingRefs.current[jobId];
          addToast(`✅ "${docResp.data.filename}" processed successfully`, 'success');
        } else if (job.status === 'failed') {
          clearInterval(pollingRefs.current[jobId]);
          delete pollingRefs.current[jobId];
          addToast(`❌ Processing failed: ${job.error_message || 'Unknown error'}`, 'error');
        }
      } catch {
        // Ignore transient poll errors
      }
    }, 2000);

    pollingRefs.current[jobId] = intervalId;
  };

  // ── Handle upload ────────────────────────────────────────────────────────────
  const handleUpload = async (file) => {
    setUploading(true);
    setUploadProgress(0);

    try {
      const resp = await documentsAPI.upload(file, (progressEvent) => {
        if (progressEvent.total) {
          setUploadProgress(Math.round((progressEvent.loaded / progressEvent.total) * 100));
        }
      });

      const { document_id, job_id, message } = resp.data;

      // Refresh list to include new doc
      await loadDocuments();
      addToast(message || '📤 File uploaded — processing started', 'success');

      // Start polling
      startPolling(job_id, document_id);
    } catch (err) {
      const detail = err.response?.data?.detail || 'Upload failed. Please try again.';
      addToast(`❌ ${detail}`, 'error');
    } finally {
      setUploading(false);
      setUploadProgress(0);
    }
  };

  // ── Navigate to query ────────────────────────────────────────────────────────
  const handleQuery = (documentId) => {
    navigate(`/query?doc=${documentId}`);
  };

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <div className="page documents-page">
      <Toast toasts={toasts} onDismiss={dismissToast} />

      <div className="page-header">
        <h1 className="page-title">📁 Documents</h1>
        <p className="page-subtitle">
          Upload your business documents for multimodal RAG processing.
        </p>
      </div>

      <UploadZone
        onUpload={handleUpload}
        uploading={uploading}
        uploadProgress={uploadProgress}
      />

      <div className="document-list">
        <div className="document-list-header">
          <h2>Your Documents</h2>
          {documents.length > 0 && (
            <span className="doc-count">{documents.length} document{documents.length !== 1 ? 's' : ''}</span>
          )}
        </div>

        {loading ? (
          <div className="doc-loading">
            <div className="spinner" />
            <span>Loading documents…</span>
          </div>
        ) : documents.length === 0 ? (
          <div className="empty-state">
            <span className="empty-icon">📂</span>
            <p>No documents yet.</p>
            <p className="empty-hint">Upload your first document to get started.</p>
          </div>
        ) : (
          <div className="doc-card-list">
            {documents.map((doc) => (
              <DocumentCard
                key={doc.document_id}
                doc={doc}
                onQuery={handleQuery}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
