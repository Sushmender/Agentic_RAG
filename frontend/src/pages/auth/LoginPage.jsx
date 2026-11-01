/**
 * src/pages/auth/LoginPage.jsx
 * Redesigned login — split layout:
 *   Left: brand panel with animated pipeline SVG
 *   Right: clean login form with show/hide password, inline validation
 */

import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { PasswordInput, Input } from '../../components/ui/Input';
import { Button } from '../../components/ui/Button';
import { PipelineVisual } from './PipelineVisual';
import './AuthPage.css';

export default function LoginPage() {
  const { login } = useAuth();
  const navigate   = useNavigate();

  const [form, setForm]     = useState({ username: '', password: '' });
  const [errors, setErrors] = useState({});
  const [apiError, setApiError] = useState('');
  const [loading, setLoading]   = useState(false);

  const validate = () => {
    const e = {};
    if (!form.username.trim()) e.username = 'Username is required';
    if (!form.password)        e.password = 'Password is required';
    return e;
  };

  const handleChange = (field) => (e) => {
    setForm(prev => ({ ...prev, [field]: e.target.value }));
    if (errors[field]) setErrors(prev => ({ ...prev, [field]: '' }));
    if (apiError) setApiError('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length) { setErrors(errs); return; }

    setLoading(true);
    setApiError('');
    try {
      await login(form.username, form.password);
      navigate('/');
    } catch (err) {
      setApiError(err.response?.data?.detail || 'Login failed. Check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      {/* Left brand panel */}
      <div className="auth-brand">
        <PipelineVisual />
        <div className="auth-brand__text">
          <h1 className="auth-brand__title">Multimodal RAG</h1>
          <p className="auth-brand__sub">
            Retrieve from text, tables, figures, and images — all in one pipeline.
          </p>
        </div>
      </div>

      {/* Right form panel */}
      <div className="auth-form-panel">
        <div className="auth-card">
          <div className="auth-card__header">
            <h2 className="auth-card__title">Welcome back</h2>
            <p className="auth-card__sub">Sign in to your account to continue</p>
          </div>

          <form className="auth-form" onSubmit={handleSubmit} noValidate>
            <Input
              label="Username"
              id="login-username"
              type="text"
              placeholder="your_username"
              value={form.username}
              onChange={handleChange('username')}
              error={errors.username}
              autoFocus
              autoComplete="username"
            />

            <PasswordInput
              label="Password"
              id="login-password"
              placeholder="••••••••"
              value={form.password}
              onChange={handleChange('password')}
              error={errors.password}
              autoComplete="current-password"
            />

            {apiError && (
              <div className="auth-api-error" role="alert">
                {apiError}
              </div>
            )}

            <Button
              type="submit"
              variant="primary"
              size="lg"
              loading={loading}
              style={{ width: '100%', marginTop: '8px' }}
            >
              Sign In
            </Button>
          </form>

          <p className="auth-switch">
            Don't have an account?{' '}
            <Link to="/register" className="auth-switch__link">Create one</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
