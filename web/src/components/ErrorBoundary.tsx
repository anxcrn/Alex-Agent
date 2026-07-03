import { Component, type ReactNode, type ErrorInfo } from "react";
import { Link } from "react-router-dom";

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

/**
 * Global error boundary that catches React render crashes (e.g. when the
 * backend API is unreachable) and shows a friendly recovery UI instead of
 * a blank white page.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("[ErrorBoundary] Caught:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      const errorMessage = this.state.error?.message ?? "Unknown error";
      const isNetworkError =
        errorMessage.includes("fetch") ||
        errorMessage.includes("network") ||
        errorMessage.includes("Failed to fetch") ||
        errorMessage.includes("NetworkError") ||
        errorMessage.includes("ECONNREFUSED") ||
        errorMessage.includes("ERR_CONNECTION_REFUSED");

      return (
        <div className="flex min-h-[60vh] flex-col items-center justify-center gap-6 px-6 text-center">
          <div className="space-y-3">
            <div className="text-4xl">⚠️</div>
            <h2 className="text-xl font-bold tracking-wide uppercase text-white">
              {isNetworkError ? "Backend Not Connected" : "Something Went Wrong"}
            </h2>
            <p className="max-w-md text-sm text-white/60 leading-relaxed">
              {isNetworkError
                ? "The Alex Agent dashboard backend is not running. Start it with 'alex dashboard' or configure your API key first."
                : `An error occurred: ${errorMessage}`}
            </p>
          </div>
          <div className="flex gap-3">
            <Link
              to="/"
              onClick={() => this.setState({ hasError: false, error: null })}
              className="px-5 py-2.5 text-xs font-bold uppercase tracking-wider bg-[#BF5FFF]/20 border border-[#BF5FFF]/50 hover:bg-[#BF5FFF] text-white rounded-sm transition-all duration-300"
            >
              Back to Home
            </Link>
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null });
                window.location.reload();
              }}
              className="px-5 py-2.5 text-xs font-bold uppercase tracking-wider bg-white/5 border border-white/10 hover:bg-white/10 text-white rounded-sm transition-all duration-300"
            >
              Retry
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
