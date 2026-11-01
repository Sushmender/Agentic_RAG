/**
 * src/components/PageEvidence.jsx
 * P-2 · Evidence panel: real bounding boxes on the actual page
 * - Fetches rendered page as blob with JWT via axios
 * - Caches object URLs by (documentId, page) and revokes on unmount
 * - Overlays real normalized bboxes [left, top, right, bottom] in percent
 * - Highlights active source with rank badge; dims other chunks on same page
 * - Click to open lightbox with zoom controls
 * - Skeleton while loading and fallback to text view on error
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { ZoomIn, ZoomOut, RotateCcw, X, Maximize2 } from 'lucide-react';
import { documentsAPI } from '../services/api';
import { formatRelevance } from '../utils/relevance';
import './PageEvidence.css';

// Module-level cache to share page renders across source cards
const blobCache = new Map();

export function revokeAllPageBlobUrls() {
  for (const url of blobCache.values()) {
    try {
      URL.revokeObjectURL(url);
    } catch {}
  }
  blobCache.clear();
}

export function PageEvidence({
  documentId,
  page = 0,
  activeChunkId,
  chunksOnPage = [],
  activeRank = 1,
  isFocused = false,
  filename = '',
  onError,
}) {
  const cacheKey = `${documentId}:${page}`;
  const [imageUrl, setImageUrl] = useState(() => blobCache.get(cacheKey) || null);
  const [loading, setLoading] = useState(!blobCache.has(cacheKey));
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [zoomLevel, setZoomLevel] = useState(1);
  const activeBoxRef = useRef(null);

  // Focus active box on demand
  useEffect(() => {
    if (isFocused && activeBoxRef.current) {
      activeBoxRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [isFocused]);

  // Load page image blob
  useEffect(() => {
    let isMounted = true;

    if (blobCache.has(cacheKey)) {
      setImageUrl(blobCache.get(cacheKey));
      setLoading(false);
      return;
    }

    setLoading(true);
    documentsAPI
      .getPageImage(documentId, page)
      .then((res) => {
        if (!isMounted) return;
        const url = URL.createObjectURL(res.data);
        blobCache.set(cacheKey, url);
        setImageUrl(url);
        setLoading(false);
      })
      .catch((err) => {
        if (!isMounted) return;
        setLoading(false);
        if (onError) onError(err);
      });

    return () => {
      isMounted = false;
    };
  }, [documentId, page, cacheKey, onError]);

  // Keyboard shortcut (Escape) to close lightbox
  useEffect(() => {
    if (!lightboxOpen) return;
    const handleKey = (e) => {
      if (e.key === 'Escape') setLightboxOpen(false);
      if (e.key === '+' || e.key === '=') setZoomLevel((z) => Math.min(z + 0.25, 3));
      if (e.key === '-') setZoomLevel((z) => Math.max(z - 0.25, 0.75));
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [lightboxOpen]);

  const renderOverlays = useCallback(
    (isLightbox = false) => {
      if (!chunksOnPage?.length) return null;

      return chunksOnPage.map((chunk) => {
        const bbox = chunk.bbox;
        if (!bbox || bbox.length !== 4) return null;

        const left = `${Math.max(0, Math.min(1, bbox[0])) * 100}%`;
        const top = `${Math.max(0, Math.min(1, bbox[1])) * 100}%`;
        const width = `${Math.max(0.01, Math.min(1, bbox[2] - bbox[0])) * 100}%`;
        const height = `${Math.max(0.01, Math.min(1, bbox[3] - bbox[1])) * 100}%`;

        const isActive = chunk.chunk_id === activeChunkId;
        const rank = chunk.rank || activeRank;
        const isNearTop = (bbox[1] || 0) < 0.045;

        return (
          <div
            key={chunk.chunk_id || rank}
            ref={isActive && !isLightbox ? activeBoxRef : null}
            className={`bbox-overlay ${
              isActive
                ? `bbox-overlay--active ${isFocused ? 'bbox-overlay--focused' : ''}`
                : 'bbox-overlay--dimmed'
            }`}
            style={{ left, top, width, height }}
            title={`Source #${rank} (${formatRelevance(chunk.relevance_score).label}, raw: ${formatRelevance(chunk.relevance_score).raw})`}
          >
            <span
              className={`bbox-overlay__badge ${
                isNearTop ? 'bbox-overlay__badge--below' : 'bbox-overlay__badge--above'
              }`}
            >
              #{rank}
            </span>
          </div>
        );
      });
    },
    [chunksOnPage, activeChunkId, activeRank, isFocused]
  );

  if (loading) {
    return (
      <div className="page-evidence__skeleton skeleton">
        <span className="sr-only">Loading page preview…</span>
      </div>
    );
  }

  if (!imageUrl) {
    return null;
  }

  return (
    <div className="page-evidence">
      {/* Clickable viewport */}
      <div
        className="page-evidence__viewport"
        onClick={() => setLightboxOpen(true)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && setLightboxOpen(true)}
        aria-label="Click to zoom page evidence"
        title="Click to open page in zoom lightbox"
      >
        <img
          src={imageUrl}
          alt={`Document page ${page + 1}`}
          className="page-evidence__img"
        />
        {renderOverlays(false)}
      </div>

      <div className="page-evidence__footer">
        <span>Page {page + 1} of {filename || 'document'}</span>
        <button
          type="button"
          className="page-evidence__zoom-hint"
          onClick={() => setLightboxOpen(true)}
          aria-label="Zoom in"
        >
          <Maximize2 size={12} />
          <span>Zoom</span>
        </button>
      </div>

      {/* Lightbox Modal */}
      {lightboxOpen && (
        <div
          className="evidence-lightbox"
          role="dialog"
          aria-modal="true"
          aria-label="Page Evidence Lightbox"
          onClick={() => setLightboxOpen(false)}
        >
          <div
            className="evidence-lightbox__header"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="evidence-lightbox__title">
              <span>{filename || 'Document'}</span>
              <span className="badge badge-accent2">Page {page + 1}</span>
            </div>
            <div className="evidence-lightbox__controls">
              <button
                className="evidence-lightbox__btn"
                onClick={() => setZoomLevel((z) => Math.min(z + 0.25, 3))}
                aria-label="Zoom in"
                title="Zoom in (+)"
              >
                <ZoomIn size={14} />
              </button>
              <button
                className="evidence-lightbox__btn"
                onClick={() => setZoomLevel((z) => Math.max(z - 0.25, 0.75))}
                aria-label="Zoom out"
                title="Zoom out (-)"
              >
                <ZoomOut size={14} />
              </button>
              <button
                className="evidence-lightbox__btn"
                onClick={() => setZoomLevel(1)}
                aria-label="Reset zoom"
                title="Reset zoom (1x)"
              >
                <RotateCcw size={14} />
                <span>{Math.round(zoomLevel * 100)}%</span>
              </button>
              <button
                className="evidence-lightbox__close"
                onClick={() => setLightboxOpen(false)}
                aria-label="Close lightbox (Esc)"
              >
                <X size={18} />
              </button>
            </div>
          </div>

          <div
            className="evidence-lightbox__content"
            onClick={() => setLightboxOpen(false)}
          >
            <div
              className="evidence-lightbox__wrapper"
              style={{ transform: `scale(${zoomLevel})` }}
              onClick={(e) => e.stopPropagation()}
            >
              <img
                src={imageUrl}
                alt={`Document page ${page + 1}`}
              />
              {renderOverlays(true)}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
