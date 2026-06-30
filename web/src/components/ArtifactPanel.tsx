import { useEffect, useState } from "react";
import { X, FileText, Code2, RefreshCw } from "lucide-react";
import { Button } from "@nous-research/ui/ui/components/button";
import { Markdown } from "./Markdown";

interface Artifact {
  name: string;
  title: string;
  content: string;
  updated_at: number;
}

export function ArtifactPanel({
  name,
  onClose,
  scopedProfile,
}: {
  name: string;
  onClose: () => void;
  scopedProfile?: string;
}) {
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [loading, setLoading] = useState(false);
  const [viewMode, setViewMode] = useState<"preview" | "code">("preview");

  const fetchArtifact = async () => {
    setLoading(true);
    try {
      const url = `/api/v1/artifacts/${name}${
        scopedProfile ? `?profile=${scopedProfile}` : ""
      }`;
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        setArtifact(data);
      }
    } catch (e) {
      console.error("Failed to load artifact", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchArtifact();
  }, [name, scopedProfile]);

  if (loading && !artifact) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-4">
        <RefreshCw className="h-6 w-6 animate-spin text-text-secondary" />
        <span className="mt-2 text-xs text-text-secondary">Loading artifact...</span>
      </div>
    );
  }

  if (!artifact) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-4">
        <span className="text-sm text-warning font-medium">Artifact not found</span>
        <Button onClick={onClose} className="mt-4">Close</Button>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden bg-background text-foreground">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b border-border/40 pb-3">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-theme-primary" />
          <h2 className="text-sm font-semibold tracking-wide truncate max-w-[200px]">
            {artifact.title || artifact.name}
          </h2>
        </div>
        <div className="flex items-center gap-1">
          {/* View Mode Toggle */}
          <div className="flex items-center gap-0.5 rounded border border-border bg-secondary/20 p-0.5 mr-2">
            <button
              onClick={() => setViewMode("preview")}
              className={`rounded px-2 py-1 text-xs font-medium transition-colors ${
                viewMode === "preview"
                  ? "bg-secondary text-foreground shadow-sm"
                  : "text-text-secondary hover:text-foreground"
              }`}
            >
              <span className="flex items-center gap-1">
                <FileText className="h-3 w-3" />
                Preview
              </span>
            </button>
            <button
              onClick={() => setViewMode("code")}
              className={`rounded px-2 py-1 text-xs font-medium transition-colors ${
                viewMode === "code"
                  ? "bg-secondary text-foreground shadow-sm"
                  : "text-text-secondary hover:text-foreground"
              }`}
            >
              <span className="flex items-center gap-1">
                <Code2 className="h-3 w-3" />
                Code
              </span>
            </button>
          </div>

          <Button ghost size="icon" onClick={onClose} aria-label="Close panel">
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Content area */}
      <div className="min-h-0 flex-1 overflow-y-auto p-4 select-text">
        {viewMode === "preview" ? (
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <Markdown content={artifact.content} />
          </div>
        ) : (
          <pre className="rounded border border-border bg-secondary/40 p-4 text-xs font-mono leading-relaxed overflow-x-auto">
            <code>{artifact.content}</code>
          </pre>
        )}
      </div>
    </div>
  );
}
