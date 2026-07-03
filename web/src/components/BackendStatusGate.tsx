import { type ReactNode } from "react";

interface BackendStatusGateProps {
  children: ReactNode;
}

export function BackendStatusGate({ children }: BackendStatusGateProps) {
  // Always render children so the user can access the chat interface and demo mode immediately.
  return <>{children}</>;
}
