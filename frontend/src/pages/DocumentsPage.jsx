/**
 * src/pages/DocumentsPage.jsx
 * Redesigned with:
 *   - Large animated dropzone with dashed border
 *   - Per-file pipeline stage stepper (Upload → Parse → Chunk → Embed → Index)
 *   - Grid/list toggle with file-type icons, doc ID chip, copy-to-clipboard
 *   - Slide-over drawer for details
 *   - Confirm dialog for delete (no window.confirm)
 *   - Search + sort above list
 *   - Full skeleton, empty, error states
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDropzone } from 'react-dropzone';
import { toast } from 'sonner';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Upload, FileText, FileSpreadsheet, Presentation, Image,
  Search, Copy, Check, Trash2, MessageSquare, LayoutGrid,
  List, X, Info, AlertCircle, ArrowUpDown,
  FileArchive,
} from 'lucide-react';
import { documentsAPI, jobsAPI } from '../services/api';
import { StatusBadge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { Skeleton } from '../components/ui/Skeleton';
import { EmptyState } from '../components/ui/EmptyState';
import './DocumentsPage.css';

/* ── Constants ─────────────────────────────────────────────── */

const ACCEPT = {
  'application/pdf': ['.pdf'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
  'image/png': ['.png'],
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/webp': ['.webp'],
};

const FILE_TYPE_META = {
  pdf:  { icon: FileText,       color: '#FF5C7A', label: 'PDF' },
  docx: { icon: FileText,       color: '#4CC9F0', label: 'DOCX' },
  pptx: { icon: Presentation,   color: '#FFB547', label: 'PPTX' },
  xlsx: { icon: FileSpreadsheet, color: '#2DE2A6', label: 'XLSX' },
  png:  { icon: Image,          color: '#7C6CF0', label: 'PNG' },
  jpg:  { icon: Image,          color: '#7C6CF0', label: 'JPG' },
  jpeg: { icon: Image,          color: '#7C6CF0', label: 'JPEG' },
  webp: { icon: Image,          color: '#7C6CF0', label: 'WEBP' },
};

const PIPELINE_STAGES = ['Upload', 'Parse', 'Chunk', 'Embed', 'Index'];

const SORT_OPTIONS = [
  { value: 'newest',  label: 'Newest first' },
  { value: 'name',    label: 'Name A–Z' },
  { value: 'size',    label: 'Largest first' },
];

/* ── Helpers ────────────────────────────────────────────────── */

function statusToStage(status) {
  switch (status) {
    case 'pending':    return 0;
    case 'processing': return 2;
    case 'completed':  return 4;
    case 'failed':     return -1;
    default:           return 0;
  }
}

/* ── Copy-to-clipboard chip ─────────────────────────────────── */
function CopyChip({ value, label }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async (e) => {
    e.stopPropagation();
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button className="copy-chip" onClick={handleCopy} title={`Copy: ${value}`} aria-label={`Copy ${label}`}>
      <span className="copy-chip__value">{value.slice(0, 12)}…</span>
      {copied ? <Check size={11} /> : <Copy size={11} />}
    </button>
  );
}

/* ── Pipeline stage stepper ─────────────────────────────────── */
function PipelineStepper({ status }) {
  const stage   = statusToStage(status);
  const failed  = status === 'failed';
  return (
    <div className="pipeline-stepper">
      {PIPELINE_STAGES.map((s, i) => {
        const done    = !failed && stage >= i;
        const active  = !failed && stage === i && status === 'processing';
        const errored = failed && i === stage || (failed && i <= 2);
        return (
          <div key={s} className="pipeline-stepper__step">
            <div className={`step-dot ${done ? 'step-dot--done' : ''} ${active ? 'step-dot--active' : ''} ${errored ? 'step-dot--error' : ''}`} />
            <span className="step-label">{s}</span>
            {i < PIPELINE_STAGES.length - 1 && (
              <div className={`step-line ${done && stage > i ? 'step-line--done' : ''}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ── Document card (grid or list) ───────────────────────────── */
function DocumentCard({ doc, onQuery, onDelete, onViewDetails, view }) {
  const typeMeta = FILE_TYPE_META[doc.document_type] || { icon: FileArchive, color: 'var(--text-secondary)', label: doc.document_type?.toUpperCase() };
  const Icon     = typeMeta.icon;
  const sizeKB   = (doc.file_size_bytes / 1024).toFixed(1);

  if (view === 'grid') {
    return (
      <motion.div
        className="doc-grid-card"
        layout
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.96 }}
      >
        <div className="doc-grid-card__header">
          <div className="doc-grid-card__type-icon" style={{ color: typeMeta.color, background: `${typeMeta.color}18` }}>
            <Icon size={20} />
          </div>
          <StatusBadge status={doc.status} />
        </div>
        <div className="doc-grid-card__name" title={doc.filename}>{doc.filename}</div>
        <div className="doc-grid-card__meta">
          <span className="doc-meta-chip">{typeMeta.label}</span>
          <span className="doc-meta-chip">{sizeKB} KB</span>
          {doc.chunk_count > 0 && (
            <span className="doc-meta-chip doc-meta-chip--accent">{doc.chunk_count} chunks</span>
          )}
        </div>
        {(doc.status === 'processing' || doc.status === 'pending') && (
          <PipelineStepper status={doc.status} />
        )}
        <div className="doc-grid-card__actions">
          {doc.status === 'completed' && (
            <Button variant="secondary" size="sm" icon={<MessageSquare size={12} />} onClick={() => onQuery(doc.document_id)}>
              Query
            </Button>
          )}
          <Button variant="ghost" size="sm" iconOnly icon={<Info size={14} />} onClick={() => onViewDetails(doc)} aria-label="View details">
            Details
          </Button>
          <Button variant="ghost" size="sm" iconOnly icon={<Trash2 size={14} />} onClick={() => onDelete(doc)} aria-label="Delete document" style={{ color: 'var(--danger)' }}>
            Delete
          </Button>
        </div>
      </motion.div>
    );
  }

  // List view
  return (
    <motion.div
      className="doc-list-row"
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
    >
      <div className="doc-list-row__icon" style={{ color: typeMeta.color, background: `${typeMeta.color}18` }}>
        <Icon size={16} />
      </div>
      <div className="doc-list-row__info">
        <span className="doc-list-row__name" title={doc.filename}>{doc.filename}</span>
        <span className="doc-list-row__meta">{typeMeta.label} · {sizeKB} KB{doc.chunk_count > 0 ? ` · ${doc.chunk_count} chunks` : ''}</span>
      </div>
      {doc.document_id && <CopyChip value={doc.document_id} label="Document ID" />}
      <StatusBadge status={doc.status} />
      <div className="doc-list-row__actions">
        {doc.status === 'completed' && (
          <Button variant="ghost" size="sm" iconOnly icon={<MessageSquare size={14} />} onClick={() => onQuery(doc.document_id)} aria-label="Query this document">
            Query
          </Button>
        )}
        <Button variant="ghost" size="sm" iconOnly icon={<Info size={14} />} onClick={() => onViewDetails(doc)} aria-label="View details">
          Details
        </Button>
        <Button variant="ghost" size="sm" iconOnly icon={<Trash2 size={14} />} onClick={() => onDelete(doc)} aria-label="Delete" style={{ color: 'var(--danger)' }}>
          Delete
        </Button>
      </div>
    </motion.div>
  );
}

/* ── Document skeletons ─────────────────────────────────────── */
function DocSkeleton({ view }) {
  if (view === 'grid') {
    return (
      <div className="doc-grid-card doc-grid-card--skeleton">
        <Skeleton width="100%" height="40px" />
        <Skeleton width="80%" height="16px" style={{ marginTop: '8px' }} />
        <Skeleton width="60%" height="12px" style={{ marginTop: '4px' }} />
      </div>
    );
  }
  return (
    <div className="doc-list-row doc-list-row--skeleton">
      <Skeleton variant="circle" width="32px" height="32px" />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '4px' }}>
        <Skeleton width="60%" height="14px" />
        <Skeleton width="40%" height="12px" />
      </div>
      <Skeleton width="60px" height="22px" />
    </div>
  );
}

/* ── Details drawer ─────────────────────────────────────────── */
function DetailsDrawer({ doc, onClose }) {
  if (!doc) return null;
  const typeMeta = FILE_TYPE_META[doc.document_type] || { label: doc.document_type?.toUpperCase() };
  const sizeKB   = (doc.file_size_bytes / 1024).toFixed(1);

  return (
    <AnimatePresence>
      {doc && (
        <>
          <motion.div
            className="drawer-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.aside
            className="drawer"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 320, damping: 32 }}
            aria-label="Document details"
          >
            <div className="drawer__header">
              <h2 className="drawer__title">Document Details</h2>
              <Button variant="ghost" size="sm" iconOnly onClick={onClose} aria-label="Close drawer">
                <X size={16} />
              </Button>
            </div>
            <div className="drawer__body">
              <div className="drawer-field"><span className="drawer-label">Filename</span><span className="drawer-value">{doc.filename}</span></div>
              <div className="drawer-field"><span className="drawer-label">File Type</span><span className="drawer-value">{typeMeta.label}</span></div>
              <div className="drawer-field"><span className="drawer-label">File Size</span><span className="drawer-value">{sizeKB} KB</span></div>
              <div className="drawer-field"><span className="drawer-label">Status</span><StatusBadge status={doc.status} /></div>
              {doc.chunk_count > 0 && (
                <div className="drawer-field"><span className="drawer-label">Chunks</span><span className="drawer-value mono">{doc.chunk_count}</span></div>
              )}
              {doc.parser_version && (
                <div className="drawer-field"><span className="drawer-label">Parser</span><span className="drawer-value mono">{doc.parser_version}</span></div>
              )}
              {doc.ade_credits_used > 0 && (
                <div className="drawer-field"><span className="drawer-label">ADE Credits</span><span className="drawer-value mono">{doc.ade_credits_used.toFixed(2)}</span></div>
              )}
              {doc.embedding_model && (
                <div className="drawer-field"><span className="drawer-label">Embed Model</span><span className="drawer-value mono">{doc.embedding_model.replace(':free', '')}</span></div>
              )}
              <div className="drawer-field">
                <span className="drawer-label">Document ID</span>
                <CopyChip value={doc.document_id} label="Document ID" />
              </div>
              {doc.error_message && (
                <div className="drawer-error">
                  <AlertCircle size={14} />
                  {doc.error_message}
                </div>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

/* ── Upload zone ────────────────────────────────────────────── */
function UploadZone({ onUpload, uploading, uploadProgress }) {
  const onDrop = useCallback((accepted, rejected) => {
    if (rejected.length > 0) {
      const reason = rejected[0].errors?.[0]?.message || 'Unsupported file type or size.';
      toast.error(reason);
      return;
    }
    if (accepted.length > 0) onUpload(accepted[0]);
  }, [onUpload]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    multiple: false,
    disabled: uploading,
    accept: ACCEPT,
    maxSize: 50 * 1024 * 1024, // 50MB
  });

  return (
    <div
      {...getRootProps()}
      className={`upload-zone ${isDragActive ? 'upload-zone--active' : ''} ${uploading ? 'upload-zone--uploading' : ''}`}
    >
      <input {...getInputProps()} id="file-upload-input" />
      <div className="upload-zone__inner">
        <div className={`upload-zone__icon ${isDragActive ? 'animate-pulse' : ''}`}>
          <Upload size={28} strokeWidth={1.5} />
        </div>
        {uploading ? (
          <>
            <p className="upload-zone__label">Uploading…</p>
            <div className="upload-zone__progress-bar">
              <div className="upload-zone__progress-fill" style={{ width: `${uploadProgress}%` }} />
            </div>
            <p className="upload-zone__hint">{uploadProgress}%</p>
          </>
        ) : (
          <>
            <p className="upload-zone__label">
              {isDragActive ? 'Drop your file here' : 'Drag & drop or click to browse'}
            </p>
            <div className="upload-zone__chips">
              {['PDF', 'DOCX', 'PPTX', 'XLSX', 'PNG', 'JPG', 'WEBP'].map(t => (
                <span key={t} className="upload-type-chip">{t}</span>
              ))}
            </div>
            <p className="upload-zone__hint">Max 50 MB</p>
          </>
        )}
      </div>
    </div>
  );
}

/* ── Main page ──────────────────────────────────────────────── */
export default function DocumentsPage() {
  const navigate        = useNavigate();
  const [documents, setDocuments]     = useState([]);
  const [uploading, setUploading]     = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [loading, setLoading]         = useState(true);
  const [loadError, setLoadError]     = useState(null);
  const [view, setView]               = useState('list'); // 'grid' | 'list'
  const [search, setSearch]           = useState('');
  const [sort, setSort]               = useState('newest');
  const [deleteTarget, setDeleteTarget] = useState(null); // doc object
  const [drawerDoc, setDrawerDoc]     = useState(null);
  const pollingRefs = useRef({});

  /* Load documents */
  const loadDocuments = useCallback(async () => {
    setLoadError(null);
    try {
      const resp = await documentsAPI.list();
      setDocuments(resp.data.documents || []);
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to load documents. Is the backend running?';
      setLoadError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDocuments();
    const activePolls = pollingRefs.current;
    return () => { Object.values(activePolls).forEach(clearInterval); };
  }, [loadDocuments]);

  /* Poll job status */
  const startPolling = useCallback((jobId, documentId) => {
    if (pollingRefs.current[jobId]) return;
    const intervalId = setInterval(async () => {
      try {
        const jobResp = await jobsAPI.getJob(jobId);
        const job     = jobResp.data;
        const docResp = await documentsAPI.get(documentId);
        setDocuments(prev => prev.map(d => d.document_id === documentId ? docResp.data : d));
        if (job.status === 'completed') {
          clearInterval(intervalId);
          delete pollingRefs.current[jobId];
          toast.success(`"${docResp.data.filename}" indexed — ${docResp.data.chunk_count ?? 0} chunks`);
        } else if (job.status === 'failed') {
          clearInterval(intervalId);
          delete pollingRefs.current[jobId];
          toast.error(`Processing failed: ${job.error_message || 'Unknown error'}`);
        }
      } catch { /* ignore transient errors */ }
    }, 2000);
    pollingRefs.current[jobId] = intervalId;
  }, []);

  /* Handle upload */
  const handleUpload = async (file) => {
    setUploading(true);
    setUploadProgress(0);
    const toastId = toast.loading(`Uploading "${file.name}"…`);
    try {
      const resp = await documentsAPI.upload(file, (ev) => {
        if (ev.total) setUploadProgress(Math.round((ev.loaded / ev.total) * 100));
      });
      const { document_id, job_id, status: uploadStatus } = resp.data;
      toast.dismiss(toastId);
      if (uploadStatus === 'completed') {
        toast.info(`"${file.name}" already processed — returning existing record.`);
      } else {
        toast.success(`"${file.name}" uploaded! Processing in background…`);
      }
      await loadDocuments();
      startPolling(job_id, document_id);
    } catch (err) {
      toast.dismiss(toastId);
      const status = err.response?.status;
      let detail = err.response?.data?.detail || 'Upload failed.';
      if (status === 413) detail = 'File too large. Maximum is 50 MB.';
      if (status === 415) detail = 'Unsupported file type.';
      toast.error(detail);
    } finally {
      setUploading(false);
      setUploadProgress(0);
    }
  };

  /* Navigate to query */
  const handleQuery = (documentId) => navigate(`/query?doc=${documentId}`);

  /* Delete with undo */
  const confirmDelete = async () => {
    if (!deleteTarget) return;
    const { document_id, filename } = deleteTarget;
    const snapshot = [...documents];
    setDocuments(prev => prev.filter(d => d.document_id !== document_id));
    setDeleteTarget(null);
    try {
      await documentsAPI.delete(document_id);
      toast.success(`"${filename}" deleted.`, {
        action: {
          label: 'Undo',
          onClick: () => {
            setDocuments(snapshot);
            toast.info('Deletion undone — note: data may still be removed from backend.');
          },
        },
      });
    } catch {
      setDocuments(snapshot);
      toast.error(`Failed to delete "${filename}".`);
    }
  };

  /* Filter + sort */
  const displayed = documents
    .filter(d => {
      if (!search.trim()) return true;
      return d.filename.toLowerCase().includes(search.toLowerCase());
    })
    .sort((a, b) => {
      if (sort === 'name')   return a.filename.localeCompare(b.filename);
      if (sort === 'size')   return (b.file_size_bytes || 0) - (a.file_size_bytes || 0);
      // newest: by document_id (UUID v4 is time-sortable enough here)
      return b.document_id?.localeCompare(a.document_id || '') || 0;
    });

  return (
    <div className="docs-page">
      {/* Upload zone */}
      <UploadZone onUpload={handleUpload} uploading={uploading} uploadProgress={uploadProgress} />

      {/* List section */}
      <div className="docs-section">
        {/* Toolbar */}
        <div className="docs-toolbar">
          <div className="docs-toolbar__left">
            <h2 className="docs-toolbar__title">
              Your Documents
              {documents.length > 0 && (
                <span className="docs-toolbar__count">{documents.length}</span>
              )}
            </h2>
          </div>
          <div className="docs-toolbar__right">
            <div className="search-box">
              <Search size={14} className="search-box__icon" />
              <input
                type="text"
                className="search-box__input"
                placeholder="Search documents…"
                value={search}
                onChange={e => setSearch(e.target.value)}
                aria-label="Search documents"
              />
            </div>
            <div className="sort-select-wrap">
              <ArrowUpDown size={13} />
              <select
                className="sort-select"
                value={sort}
                onChange={e => setSort(e.target.value)}
                aria-label="Sort documents"
              >
                {SORT_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div className="view-toggle">
              <button
                className={`view-toggle__btn ${view === 'list' ? 'view-toggle__btn--active' : ''}`}
                onClick={() => setView('list')}
                aria-label="List view"
                aria-pressed={view === 'list'}
              >
                <List size={15} />
              </button>
              <button
                className={`view-toggle__btn ${view === 'grid' ? 'view-toggle__btn--active' : ''}`}
                onClick={() => setView('grid')}
                aria-label="Grid view"
                aria-pressed={view === 'grid'}
              >
                <LayoutGrid size={15} />
              </button>
            </div>
          </div>
        </div>

        {/* Error */}
        {loadError && (
          <div className="docs-error-banner" role="alert">
            <AlertCircle size={15} />
            {loadError}
            <Button variant="ghost" size="sm" onClick={() => { setLoading(true); loadDocuments(); }}>
              Retry
            </Button>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className={view === 'grid' ? 'docs-grid' : 'docs-list'}>
            {[1,2,3].map(i => <DocSkeleton key={i} view={view} />)}
          </div>
        )}

        {/* Empty */}
        {!loading && !loadError && displayed.length === 0 && (
          documents.length === 0 ? (
            <EmptyState
              icon={<Upload size={24} />}
              title="No documents yet"
              description="Drag & drop a file above or click to browse. Supports PDF, DOCX, PPTX, XLSX, and images."
            />
          ) : (
            <EmptyState
              icon={<Search size={24} />}
              title="No results"
              description={`No documents match "${search}"`}
            />
          )
        )}

        {/* Document list / grid */}
        {!loading && displayed.length > 0 && (
          <div className={view === 'grid' ? 'docs-grid' : 'docs-list'}>
            <AnimatePresence>
              {displayed.map(doc => (
                <DocumentCard
                  key={doc.document_id}
                  doc={doc}
                  view={view}
                  onQuery={handleQuery}
                  onDelete={setDeleteTarget}
                  onViewDetails={setDrawerDoc}
                />
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>

      {/* Delete confirm modal */}
      <Modal
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title="Delete Document"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button variant="danger" onClick={confirmDelete}>Delete</Button>
          </>
        }
      >
        <p style={{ color: 'var(--text-secondary)', fontSize: '14px', lineHeight: 1.6 }}>
          Are you sure you want to delete <strong style={{ color: 'var(--text-primary)' }}>"{deleteTarget?.filename}"</strong>?
          All chunks and embeddings will be permanently removed.
        </p>
      </Modal>

      {/* Details slide-over drawer */}
      <DetailsDrawer doc={drawerDoc} onClose={() => setDrawerDoc(null)} />
    </div>
  );
}
