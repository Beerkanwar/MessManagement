import React, { Component, ErrorInfo } from 'react';
import { ErrorState } from './ErrorState';

interface ErrorBoundaryProps {
  children: React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Log exception safely without exposing credentials
    console.error('Route error boundary caught an exception:', error.message, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      const appErr = this.state.error as any;
      const errorCode = appErr?.code || 'UNEXPECTED_ERROR';
      const message = appErr?.message || 'An unexpected rendering error occurred in this view.';
      const traceId = appErr?.traceId || 'trace-boundary-' + Math.random().toString(36).substring(2, 9);

      return (
        <div className="p-8 flex items-center justify-center min-h-[50vh]">
          <ErrorState
            errorCode={errorCode}
            message={message}
            traceId={traceId}
            onRetry={() => this.setState({ hasError: false, error: null })}
          />
        </div>
      );
    }

    return this.props.children;
  }
}
