/**
 * frontend/src/main.jsx
 * React app entry point.
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { Toaster } from 'sonner';
import './index.css';
import App from './App.jsx';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
    <Toaster
      position="bottom-right"
      richColors
      closeButton
      toastOptions={{
        duration: 4500,
        style: {
          fontFamily: 'Inter, sans-serif',
          fontSize: '0.875rem',
        },
      }}
    />
  </StrictMode>,
);
