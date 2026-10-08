/**
 * frontend/src/pages/DocumentsPage.jsx
 * Day 1–9 — Full implementation:
 *   - Drag-and-drop upload via react-dropzone
 *   - Upload progress + job status polling (2s interval)
 *   - Document list with color-coded status badges
 *   - View Details panel: chunk count, chunk types, ADE credits, parser version
 *   - Empty state, skeleton loading, sonner toast notifications, error banner
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDropzone } from 'react-dropzone';
import { toast } from 'sonner';
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
function DocumentCard({ doc, onQuery, onDelete }) {
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
                  {doc.embedding_model && (
                    <div className="details-item">
                      <span className="details-label">Embedding Model</span>
                      <span className="details-value details-value--code">
                        🧠 {doc.embedding_model.replace(':free', '')}
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
        <div className="doc-card__action-group">
          {doc.status === 'completed' && (
            <button
              className="doc-card__query-btn"
              onClick={() => onQuery(doc.document_id)}
            >
              Query →
            </button>
          )}
          <button
            className="doc-card__delete-btn"
            title="Delete document"
            onClick={() => onDelete(doc.document_id, doc.filename)}
          >
            🗑️
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Skeleton loader for document cards ────────────────────────────────────────
function DocCardSkeleton() {
  return (
    <div className="doc-card doc-card--skeleton">
      <div className="skeleton skeleton-icon" />
      <div className="doc-card__body">
        <div className="skeleton skeleton-title" />
        <div className="skeleton skeleton-meta" />
      </div>
      <div className="doc-card__right">
        <div className="skeleton skeleton-badge" />
      </div>
    </div>
  );
}

// ── Network error banner ───────────────────────────────────────────────────────
function ErrorBanner({ message, onRetry }) {
  return (
    <div className="error-banner" role="alert">
      <span className="error-banner__icon">⚠️</span>
      <span className="error-banner__text">{message}</span>
      {onRetry && (
        <button className="error-banner__retry" onClick={onRetry}>
          Retry
        </button>
      )}
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
  const [loadError, setLoadError] = useState(null);

  // Polling refs: map of jobId → intervalId
  const pollingRefs = useRef({});

  // ── Load document list ───────────────────────────────────────────────────────
  const loadDocuments = async () => {
    setLoadError(null);
    try {
      const resp = await documentsAPI.list();
      setDocuments(resp.data.documents || []);
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to load documents. Is the backend running?';
      setLoadError(msg);
      toast.error(msg);
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
          clearInterval(intervalId);
          delete pollingRefs.current[jobId];
          toast.success(`"${docResp.data.filename}" processed successfully! 🧩 ${docResp.data.chunk_count || 0} chunks indexed.`);
        } else if (job.status === 'failed') {
          clearInterval(intervalId);
          delete pollingRefs.current[jobId];
          toast.error(`Processing failed: ${job.error_message || 'Unknown error'}`);
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

    const toastId = toast.loading(`Uploading "${file.name}"…`);

    try {
      const resp = await documentsAPI.upload(file, (progressEvent) => {
        if (progressEvent.total) {
          setUploadProgress(Math.round((progressEvent.loaded / progressEvent.total) * 100));
        }
      });

      const { document_id, job_id, status: uploadStatus } = resp.data;

      toast.dismiss(toastId);

      if (uploadStatus === 'completed') {
        // Already processed (idempotent re-upload)
        toast.info(`"${file.name}" already processed — returning existing record.`);
      } else {
        toast.success(`"${file.name}" uploaded! Processing in background…`);
      }

      // Refresh list to include new doc
      await loadDocuments();

      // Start polling
      startPolling(job_id, document_id);
    } catch (err) {
      toast.dismiss(toastId);
      const status = err.response?.status;
      let detail = err.response?.data?.detail || 'Upload failed. Please try again.';
      if (status === 413) detail = `File too large. Maximum upload size is 50 MB.`;
      if (status === 415) detail = `Unsupported file type. Allowed: PDF, DOCX, PPTX, XLSX, PNG, JPG, WEBP.`;
      toast.error(detail);
    } finally {
      setUploading(false);
      setUploadProgress(0);
    }
  };

  // ── Navigate to query ────────────────────────────────────────────────────────
  const handleQuery = (documentId) => {
    navigate(`/query?doc=${documentId}`);
  };

  // ── Delete document ──────────────────────────────────────────────────────────
  const handleDelete = async (documentId, filename) => {
    if (!window.confirm(`Delete "${filename}"? All chunks and embeddings will be removed.`)) return;
    try {
      await documentsAPI.delete(documentId);
      toast.success(`"${filename}" deleted.`);
      setDocuments((prev) => prev.filter((d) => d.document_id !== documentId));
    } catch {
      toast.error(`Failed to delete "${filename}".`);
    }
  };

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <div className="page documents-page">

      <div className="page-header">
        <h1 className="page-title">📁 Documents</h1>
        <p className="page-subtitle">
          Upload your business documents for multimodal RAG processing.
        </p>
      </div>

      {loadError && (
        <ErrorBanner
          message={loadError}
          onRetry={() => { setLoading(true); loadDocuments(); }}
        />
      )}

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
          <div className="doc-card-list">
            {[1, 2, 3].map(i => <DocCardSkeleton key={i} />)}
          </div>
        ) : !loadError && documents.length === 0 ? (
          <div className="empty-state empty-state--full">
            <span className="empty-icon">📂</span>
            <h3 className="empty-title">No documents yet</h3>
            <p className="empty-hint">
              Drag & drop a file above or click <strong>Choose File</strong> to upload your first document.
            </p>
            <ul className="empty-formats">
              <li>📄 PDF</li>
              <li>📝 DOCX</li>
              <li>📊 PPTX</li>
              <li>📈 XLSX</li>
              <li>🖼️ PNG / JPG / WEBP</li>
            </ul>
          </div>
        ) : (
          <div className="doc-card-list">
            {documents.map((doc) => (
              <DocumentCard
                key={doc.document_id}
                doc={doc}
                onQuery={handleQuery}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
