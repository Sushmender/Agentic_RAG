/**
 * frontend/src/pages/DocumentsPage.jsx
 * Document upload and list page.
 * Day 0: basic scaffold with placeholder content.
 * Day 1: full upload + status polling implementation.
 */

import { useState } from 'react';
import './DocumentsPage.css';

export default function DocumentsPage() {
  return (
    <div className="page documents-page">
      <div className="page-header">
        <h1 className="page-title">📁 Documents</h1>
        <p className="page-subtitle">
          Upload PDF, DOCX, PPTX, XLSX, or images for multimodal RAG processing.
        </p>
      </div>

      {/* Upload zone — Day 1 implementation */}
      <div className="upload-zone">
        <div className="upload-zone-inner">
          <span className="upload-icon">📤</span>
          <p className="upload-label">Drag & drop files here, or click to browse</p>
          <p className="upload-hint">Supported: PDF, DOCX, PPTX, XLSX, PNG, JPG, WEBP</p>
          <button className="upload-btn" disabled>
            Upload Document
          </button>
        </div>
        <div className="upload-coming-soon">
          Upload functionality available from Day 1.
        </div>
      </div>

      {/* Document list — Day 1 implementation */}
      <div className="document-list">
        <div className="document-list-header">
          <h2>Your Documents</h2>
        </div>
        <div className="empty-state">
          <span className="empty-icon">📂</span>
          <p>No documents yet. Upload your first document to get started.</p>
        </div>
      </div>
    </div>
  );
}
