/**
 * frontend/src/services/api.js
 * Axios instance for backend communication.
 * Base URL: VITE_API_BASE_URL from .env
 * Automatically injects JWT token from localStorage.
 */

import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

// Create axios instance
const api = axios.create({
  baseURL: BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
});

// Request interceptor — inject JWT token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor — handle 401 (clear token, redirect to login)
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// ── Auth endpoints ────────────────────────────────────────────────────────────

export const authAPI = {
  register: (data) => api.post('/auth/register', data),
  login: (username, password) => {
    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);
    return api.post('/auth/login', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
};

// ── Document endpoints ─────────────────────────────────────────────────────────

export const documentsAPI = {
  upload: (file, onProgress) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: onProgress,
    });
  },
  list: () => api.get('/documents/'),
  get: (documentId) => api.get(`/documents/${documentId}`),
  getChunk: (documentId, chunkId) => api.get(`/documents/${documentId}/chunks/${chunkId}`),
};

// ── Job endpoints ──────────────────────────────────────────────────────────────

export const jobsAPI = {
  getJob: (jobId) => api.get(`/jobs/${jobId}`),
};

// ── Query endpoint ─────────────────────────────────────────────────────────────

export const queryAPI = {
  query: (queryRequest) => api.post('/query', queryRequest),
};

// ── Health check ───────────────────────────────────────────────────────────────

export const healthAPI = {
  check: () => api.get('/health'),
};

export default api;
