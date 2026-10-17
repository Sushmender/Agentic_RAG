/**
 * frontend/src/App.jsx
 * Root app with React Router.
 * Routes: / → DocumentsPage, /query → QueryPage,
 *         /metrics → MetricsPage, /evaluation → EvaluationPage
 *         /login → LoginPage, /register → RegisterPage
 * D2: Error boundary, 404 page, lazy loading
 */

import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'sonner';
import { AuthProvider, useAuth } from './context/AuthContext';
import AppShell from './components/layout/AppShell';
import { ErrorBoundary } from './components/ErrorBoundary';

// Route-level code splitting
const DocumentsPage  = lazy(() => import('./pages/DocumentsPage'));
const QueryPage      = lazy(() => import('./pages/QueryPage'));
const LoginPage      = lazy(() => import('./pages/LoginPage'));
const RegisterPage   = lazy(() => import('./pages/RegisterPage'));
const MetricsPage    = lazy(() => import('./pages/MetricsPage'));
const EvaluationPage = lazy(() => import('./pages/EvaluationPage'));
const NotFoundPage   = lazy(() => import('./pages/NotFoundPage'));

// Dev UI playground (dev only)
const DevUI = lazy(() => import('./pages/DevUI'));

// Skeleton fallback for route Suspense
function PageSkeleton() {
  return (
    <div style={{ padding: '40px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {[1, 2, 3].map(i => (
        <div key={i} className="skeleton" style={{ height: '80px', borderRadius: '10px' }} />
      ))}
    </div>
  );
}

// Protected route wrapper
function PrivateRoute({ children }) {
  const { isAuthenticated } = useAuth();
  return isAuthenticated ? children : <Navigate to="/login" replace />;
}

function AppRoutes() {
  const { isAuthenticated } = useAuth();

  return (
    <Suspense fallback={<PageSkeleton />}>
      <Routes>
        {/* Public routes */}
        <Route
          path="/login"
          element={isAuthenticated ? <Navigate to="/" replace /> : <LoginPage />}
        />
        <Route
          path="/register"
          element={isAuthenticated ? <Navigate to="/" replace /> : <RegisterPage />}
        />

        {/* Dev route */}
        {import.meta.env.DEV && (
          <Route path="/dev/ui" element={<DevUI />} />
        )}

        {/* Protected routes inside AppShell */}
        <Route
          element={
            <PrivateRoute>
              <AppShell />
            </PrivateRoute>
          }
        >
          <Route path="/"           element={<DocumentsPage />} />
          <Route path="/query"      element={<QueryPage />} />
          <Route path="/metrics"    element={<MetricsPage />} />
          <Route path="/evaluation" element={<EvaluationPage />} />
        </Route>

        {/* 404 */}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <BrowserRouter>
          <AppRoutes />
          <Toaster
            position="bottom-right"
            theme="dark"
            closeButton
            offset="calc(var(--statusbar-height) + 16px)"
            toastOptions={{
              duration: 4000,
            }}
          />
        </BrowserRouter>
      </AuthProvider>
    </ErrorBoundary>
  );
}
