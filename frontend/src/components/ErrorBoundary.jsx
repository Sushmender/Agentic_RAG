/**
 * ErrorBoundary.jsx — React error boundary
 * Catches any render-time JS errors and shows a styled fallback.
 */
import { Component } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import './ErrorBoundary.css';

export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error('ErrorBoundary caught:', error, info);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <div className="error-boundary">
        <div className="error-boundary__content">
          <div className="error-boundary__icon">
            <AlertTriangle size={40} />
          </div>
          <h2 className="error-boundary__title">Something went wrong</h2>
          <p className="error-boundary__sub">
            An unexpected error occurred. The error has been logged.
          </p>
          {this.state.error?.message && (
            <pre className="error-boundary__detail">
              {this.state.error.message}
            </pre>
          )}
          <div className="error-boundary__actions">
            <button
              className="err-btn err-btn--primary"
              onClick={this.handleRetry}
              id="error-retry-btn"
            >
              <RefreshCw size={14} /> Try again
            </button>
            <button
              className="err-btn err-btn--secondary"
              onClick={() => (window.location.href = '/')}
              id="error-home-btn"
            >
              Go home
            </button>
          </div>
        </div>
      </div>
    );
  }
}
