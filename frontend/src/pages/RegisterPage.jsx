/**
 * src/pages/RegisterPage.jsx
 * Redesigned register — same split layout as Login.
 */

import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Input, PasswordInput } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { PipelineVisual } from './auth/PipelineVisual';
import { toast } from 'sonner';
import './auth/AuthPage.css';

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate      = useNavigate();

  const [form, setForm] = useState({ username: '', email: '', password: '', confirmPassword: '' });
  const [errors, setErrors] = useState({});
  const [apiError, setApiError] = useState('');
  const [loading, setLoading]   = useState(false);

  const validate = () => {
    const e = {};
    if (!form.username.trim())                      e.username = 'Username is required';
    else if (form.username.trim().length < 3)       e.username = 'Minimum 3 characters';
    if (!form.email.trim())                         e.email = 'Email is required';
    else if (!/\S+@\S+\.\S+/.test(form.email))     e.email = 'Enter a valid email address';
    if (!form.password)                             e.password = 'Password is required';
    else if (form.password.length < 8)             e.password = 'Minimum 8 characters';
    if (form.confirmPassword !== form.password)    e.confirmPassword = 'Passwords do not match';
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
      await register(form.username, form.email, form.password);
      toast.success('Account created! Please sign in.');
      navigate('/login');
    } catch (err) {
      setApiError(err.response?.data?.detail || 'Registration failed. Please try again.');
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
            <h2 className="auth-card__title">Create account</h2>
            <p className="auth-card__sub">Start using Multimodal RAG in seconds</p>
          </div>

          <form className="auth-form" onSubmit={handleSubmit} noValidate>
            <Input
              label="Username"
              id="reg-username"
              type="text"
              placeholder="your_username"
              value={form.username}
              onChange={handleChange('username')}
              error={errors.username}
              autoFocus
              autoComplete="username"
            />
            <Input
              label="Email"
              id="reg-email"
              type="email"
              placeholder="you@example.com"
              value={form.email}
              onChange={handleChange('email')}
              error={errors.email}
              autoComplete="email"
            />
            <PasswordInput
              label="Password"
              id="reg-password"
              placeholder="min 8 characters"
              value={form.password}
              onChange={handleChange('password')}
              error={errors.password}
              autoComplete="new-password"
            />
            <PasswordInput
              label="Confirm Password"
              id="reg-confirm-password"
              placeholder="••••••••"
              value={form.confirmPassword}
              onChange={handleChange('confirmPassword')}
              error={errors.confirmPassword}
              autoComplete="new-password"
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
              Create Account
            </Button>
          </form>

          <p className="auth-switch">
            Already have an account?{' '}
            <Link to="/login" className="auth-switch__link">Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
