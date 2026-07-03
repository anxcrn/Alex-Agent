import { useState } from "react";
import { ShieldAlert, Check, HelpCircle } from "lucide-react";
import { Button } from "@nous-research/ui/ui/components/button";

export interface DialogData {
  id: string;
  type: "question" | "permission";
  question?: string;
  options?: string[];
  is_multi_select?: boolean;
  reason?: string;
  action?: string;
  target?: string;
}

export function DialogModal({
  dialog,
  onResolve,
}: {
  dialog: DialogData;
  onResolve: () => void;
}) {
  const [selectedAnswers, setSelectedAnswers] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  const handleCheckboxChange = (opt: string) => {
    setSelectedAnswers((prev) =>
      prev.includes(opt) ? prev.filter((a) => a !== opt) : [...prev, opt]
    );
  };

  const handleResolveQuestion = async (answer: string | string[]) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/dialogs/${dialog.id}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answer }),
      });
      if (res.ok) {
        onResolve();
      }
    } catch (e) {
      console.error("Failed to resolve dialog", e);
    } finally {
      setLoading(false);
    }
  };

  const handleResolvePermission = async (granted: boolean) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/dialogs/${dialog.id}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ granted }),
      });
      if (res.ok) {
        onResolve();
      }
    } catch (e) {
      console.error("Failed to resolve dialog", e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="relative w-full max-w-md overflow-hidden rounded-xl border border-border bg-card shadow-2xl p-6 flex flex-col gap-4 animate-in zoom-in-95 duration-200">
        
        {/* Header Icon & Title */}
        <div className="flex items-start gap-3">
          {dialog.type === "permission" ? (
            <div className="rounded-full bg-warning/15 p-2.5 text-warning">
              <ShieldAlert className="h-6 w-6" />
            </div>
          ) : (
            <div className="rounded-full bg-theme-primary/15 p-2.5 text-theme-primary">
              <HelpCircle className="h-6 w-6" />
            </div>
          )}
          
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-bold text-foreground">
              {dialog.type === "permission" ? "Permission Request" : "Clarification Needed"}
            </h3>
            <p className="mt-1 text-xs text-text-secondary">
              The agent is waiting for your response to continue.
            </p>
          </div>
        </div>

        {/* Content body */}
        <div className="mt-2 text-sm text-foreground/90">
          {dialog.type === "permission" ? (
            <div className="flex flex-col gap-3 rounded-lg border border-border/60 bg-secondary/10 p-4">
              <div>
                <span className="text-[10px] uppercase font-bold tracking-wider text-text-secondary">Reason</span>
                <p className="mt-0.5 text-xs text-foreground font-medium">{dialog.reason}</p>
              </div>
              <div className="grid grid-cols-2 gap-2 border-t border-border/40 pt-2.5">
                <div>
                  <span className="text-[10px] uppercase font-bold tracking-wider text-text-secondary">Action</span>
                  <p className="mt-0.5 text-xs font-mono text-theme-primary">{dialog.action}</p>
                </div>
                <div>
                  <span className="text-[10px] uppercase font-bold tracking-wider text-text-secondary">Target</span>
                  <p className="mt-0.5 text-xs font-mono text-foreground truncate" title={dialog.target}>{dialog.target}</p>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              <p className="font-medium text-foreground">{dialog.question}</p>
              
              {/* Option choices */}
              {dialog.options && (
                <div className="flex flex-col gap-2">
                  {dialog.options.map((opt, i) => {
                    const isChecked = selectedAnswers.includes(opt);
                    return dialog.is_multi_select ? (
                      <label
                        key={i}
                        className={`flex items-center gap-3 rounded-lg border px-4 py-3 text-xs font-medium cursor-pointer transition-all hover:bg-secondary/20 ${
                          isChecked
                            ? "border-theme-primary bg-theme-primary/5 text-foreground"
                            : "border-border text-text-secondary"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => handleCheckboxChange(opt)}
                          className="h-3.5 w-3.5 rounded border-border text-theme-primary focus:ring-0 focus:ring-offset-0"
                        />
                        {opt}
                      </label>
                    ) : (
                      <button
                        key={i}
                        disabled={loading}
                        onClick={() => handleResolveQuestion(opt)}
                        className="w-full text-left rounded-lg border border-border px-4 py-3 text-xs font-medium text-text-secondary hover:border-theme-primary hover:text-foreground hover:bg-secondary/15 transition-all"
                      >
                        {opt}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Action Buttons */}
        <div className="flex items-center justify-end gap-2.5 mt-2 border-t border-border/40 pt-4">
          {dialog.type === "permission" ? (
            <>
              <Button
                ghost
                disabled={loading}
                onClick={() => handleResolvePermission(false)}
                className="text-xs text-text-secondary hover:text-foreground hover:bg-secondary/10"
              >
                Deny
              </Button>
              <Button
                disabled={loading}
                onClick={() => handleResolvePermission(true)}
                prefix={<Check className="h-3.5 w-3.5" />}
                className="text-xs"
              >
                Approve
              </Button>
            </>
          ) : (
            dialog.is_multi_select && (
              <Button
                disabled={loading || selectedAnswers.length === 0}
                onClick={() => handleResolveQuestion(selectedAnswers)}
                className="text-xs"
              >
                Submit Selection
              </Button>
            )
          )}
        </div>

      </div>
    </div>
  );
}
