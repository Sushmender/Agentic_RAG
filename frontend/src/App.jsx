/**
 * frontend/src/App.jsx
 * Root app with React Router.
 * Routes: / → DocumentsPage, /query → QueryPage, /login → LoginPage, /register → RegisterPage
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Navbar from './components/layout/Navbar';
import DocumentsPage from './pages/DocumentsPage';
import QueryPage from './pages/QueryPage';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import MetricsPage from './pages/MetricsPage';
import EvaluationPage from './pages/EvaluationPage';

// Protected route wrapper
function PrivateRoute({ children }) {
  const { isAuthenticated } = useAuth();
  return isAuthenticated ? children : <Navigate to="/login" replace />;
}

function AppRoutes() {
  const { isAuthenticated } = useAuth();

  return (
    <div className="app">
      {isAuthenticated && <Navbar />}
      <Routes>
        <Route path="/login" element={isAuthenticated ? <Navigate to="/" replace /> : <LoginPage />} />
        <Route path="/register" element={isAuthenticated ? <Navigate to="/" replace /> : <RegisterPage />} />
        <Route
          path="/"
          element={<PrivateRoute><DocumentsPage /></PrivateRoute>}
        />
        <Route
          path="/query"
          element={<PrivateRoute><QueryPage /></PrivateRoute>}
        />
        <Route
          path="/metrics"
          element={<PrivateRoute><MetricsPage /></PrivateRoute>}
        />
        <Route
          path="/evaluation"
          element={<PrivateRoute><EvaluationPage /></PrivateRoute>}
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  );
}
