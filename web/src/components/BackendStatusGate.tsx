import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";

interface BackendStatusGateProps {
  children: ReactNode;
}

/**
 * Checks backend connectivity and shows a friendly overlay when the
 * backend API is unreachable. Pages that don't need the backend (like
 * the landing page at "/") are excluded from the check.
 */
export function BackendStatusGate({ children }: BackendStatusGateProps) {
  const { pathname } = useLocation();
  const [status, setStatus] = useState<"checking" | "online" | "offline">("checking");
  const [retrying, setRetrying] = useState(false);

  // The landing page doesn't need backend connectivity
  const isLandingPage = pathname === "/" || pathname === "";

  useEffect(() => {
    if (isLandingPage) {
      setStatus("online"); // Don't gate the landing page
      return;
    }

    let cancelled = false;

    const checkBackend = async () => {
      try {
        const res = await fetch("/api/status", {
          method: "GET",
          signal: AbortSignal.timeout(5000),
        });
        if (!cancelled) setStatus(res.ok ? "online" : "offline");
      } catch {
        if (!cancelled) setStatus("offline");
      }
    };

    checkBackend();

    // Re-check every 10 seconds when offline
    const interval = setInterval(() => {
      if (status === "offline") {
        checkBackend();
      }
    }, 10000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [isLandingPage, pathname, status]);

  const retry = async () => {
    setRetrying(true);
    try {
      const res = await fetch("/api/status", {
        method: "GET",
        signal: AbortSignal.timeout(5000),
      });
      setStatus(res.ok ? "online" : "offline");
    } catch {
      setStatus("offline");
    }
    setRetrying(false);
  };

  // Landing page or online: render children normally
  if (isLandingPage || status === "online") {
    return <>{children}</>;
  }

  // Checking state: show a minimal loading spinner
  if (status === "checking") {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="flex items-center gap-3 text-sm text-white/50">
          <div className="size-4 border-2 border-white/20 border-t-[#BF5FFF] rounded-full animate-spin" />
          <span>Connecting to backend…</span>
        </div>
      </div>
    );
  }

  // Offline: show a styled disconnect notice
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-8 px-6 text-center">
      {/* Pulsing icon */}
      <div className="relative">
        <div className="absolute inset-0 bg-[#FF007F]/20 rounded-full blur-xl animate-pulse" />
        <div className="relative flex size-20 items-center justify-center rounded-full border border-[#FF007F]/30 bg-[#FF007F]/5">
          <svg className="size-8 text-[#FF007F]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
          </svg>
        </div>
      </div>

      {/* Message */}
      <div className="space-y-3 max-w-lg">
        <h2 className="text-xl font-bold tracking-wide uppercase text-white">
          Backend Offline
        </h2>
        <p className="text-sm text-white/50 leading-relaxed">
          The Alex Agent dashboard backend is not running on <code className="text-[#00F0FF] bg-white/5 px-1.5 py-0.5 rounded text-xs">localhost:9119</code>.
          Start it with the command below, then click retry.
        </p>
      </div>

      {/* Terminal command block */}
      <div className="w-full max-w-md bg-black/60 border border-white/10 rounded-lg p-4 font-mono text-xs">
        <div className="flex items-center gap-2 text-white/30 mb-3">
          <div className="size-2.5 rounded-full bg-[#FF5F56]" />
          <div className="size-2.5 rounded-full bg-[#FFBD2E]" />
          <div className="size-2.5 rounded-full bg-[#27C93F]" />
          <span className="ml-2">terminal</span>
        </div>
        <div className="space-y-1 text-white/70">
          <div><span className="text-[#BF5FFF]">$</span> alex dashboard</div>
          <div className="text-white/30"># Or if running from source:</div>
          <div><span className="text-[#BF5FFF]">$</span> python cli.py dashboard --no-open</div>
        </div>
      </div>

      {/* Setup hint */}
      <div className="text-xs text-white/30 max-w-md space-y-1">
        <p>⚙️ You also need an API key configured. Add it to <code className="text-white/50">~/.alex/.env</code>:</p>
        <div className="bg-black/40 border border-white/5 rounded px-3 py-2 font-mono text-left">
          GEMINI_API_KEY=your_key_here
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex gap-3 pt-2">
        <button
          onClick={retry}
          disabled={retrying}
          className="inline-flex items-center gap-2 px-6 py-3 text-xs font-bold uppercase tracking-wider bg-[#BF5FFF]/20 border border-[#BF5FFF]/50 hover:bg-[#BF5FFF] disabled:opacity-50 text-white rounded-sm transition-all duration-300"
        >
          {retrying ? (
            <>
              <div className="size-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Checking…
            </>
          ) : (
            "↻ Retry Connection"
          )}
        </button>
        <Link
          to="/"
          className="px-6 py-3 text-xs font-bold uppercase tracking-wider bg-white/5 border border-white/10 hover:bg-white/10 text-white rounded-sm transition-all duration-300"
        >
          ← Back to Home
        </Link>
      </div>
    </div>
  );
}
