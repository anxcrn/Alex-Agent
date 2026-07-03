import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Clock,
  Cpu,
  DollarSign,
  ListTodo,
  Play,
  Terminal,
  XCircle,
} from "lucide-react";
import { Button } from "@nous-research/ui/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@nous-research/ui/ui/components/card";
import { H2 } from "@nous-research/ui/ui/components/typography/h2";
import { api } from "@/lib/api";
import { useI18n } from "@/i18n";
import { usePageHeader } from "@/contexts/usePageHeader";
import { cn, themedBody } from "@/lib/utils";

interface Summary {
  total_sessions: number;
  active_sessions: number;
  total_tool_calls: number;
  total_cost_usd: number;
  recent_errors: number;
  uptime_seconds: number;
}

interface ActivityEvent {
  session_id: string;
  event_type: string;
  data: Record<string, unknown>;
  timestamp: string;
}

interface ToolCallEvent {
  session_id: string;
  tool_name: string;
  status: string;
  duration_ms: number;
  cost_usd: number;
  error: string;
  timestamp: string;
}

interface SessionInfo {
  session_id: string;
  status: string;
  started_at: string;
  tool_calls: number;
  cost_usd: number;
  total_duration_ms: number;
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString();
  } catch {
    return iso;
  }
}

function StatCard({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  color: string;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium">{label}</CardTitle>
        <Icon className={cn("h-4 w-4", color)} />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
      </CardContent>
    </Card>
  );
}

export default function AgentViewPage() {
  const { t } = useI18n();
  usePageHeader("Agent View");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [activities, setActivities] = useState<ActivityEvent[]>([]);
  const [toolCalls, setToolCalls] = useState<ToolCallEvent[]>([]);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [activeTab, setActiveTab] = useState<"overview" | "sessions" | "tools">("overview");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [summaryRes, activitiesRes, toolCallsRes, sessionsRes] = await Promise.all([
        api.get("/api/v1/agent-view/summary").catch(() => null),
        api.get("/api/v1/agent-view/activities?limit=20").catch(() => null),
        api.get("/api/v1/agent-view/tool-calls?limit=20").catch(() => null),
        api.get("/api/v1/agent-view/sessions").catch(() => null),
      ]);

      if (summaryRes?.data) setSummary(summaryRes.data);
      if (activitiesRes?.data?.activities) setActivities(activitiesRes.data.activities);
      if (toolCallsRes?.data?.tool_calls) setToolCalls(toolCallsRes.data.tool_calls);
      if (sessionsRes?.data?.sessions) setSessions(sessionsRes.data.sessions);
    } catch {
      // API not available
    }
  }, []);

  useEffect(() => {
    fetchData();
    intervalRef.current = setInterval(fetchData, 3000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchData]);

  const statusIcon = (status: string) => {
    switch (status) {
      case "running":
        return <Play className="h-4 w-4 text-green-500" />;
      case "completed":
        return <CheckCircle2 className="h-4 w-4 text-blue-500" />;
      case "error":
        return <XCircle className="h-4 w-4 text-red-500" />;
      default:
        return <Clock className="h-4 w-4 text-yellow-500" />;
    }
  };

  return (
    <div className={cn("flex flex-col gap-6 p-6", themedBody)}>
      <div className="flex items-center justify-between">
        <H2>Agent View</H2>
        <div className="flex gap-2">
          <Button
            variant={activeTab === "overview" ? "default" : "outline"}
            size="sm"
            onClick={() => setActiveTab("overview")}
          >
            <Activity className="mr-1 h-4 w-4" />
            Overview
          </Button>
          <Button
            variant={activeTab === "sessions" ? "default" : "outline"}
            size="sm"
            onClick={() => setActiveTab("sessions")}
          >
            <Terminal className="mr-1 h-4 w-4" />
            Sessions
          </Button>
          <Button
            variant={activeTab === "tools" ? "default" : "outline"}
            size="sm"
            onClick={() => setActiveTab("tools")}
          >
            <ListTodo className="mr-1 h-4 w-4" />
            Tool Calls
          </Button>
        </div>
      </div>

      {activeTab === "overview" && (
        <>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <StatCard
              icon={Terminal}
              label="Active Sessions"
              value={summary ? String(summary.active_sessions) : "—"}
              color="text-blue-500"
            />
            <StatCard
              icon={Cpu}
              label="Total Sessions"
              value={summary ? String(summary.total_sessions) : "—"}
              color="text-purple-500"
            />
            <StatCard
              icon={ListTodo}
              label="Tool Calls"
              value={summary ? String(summary.total_tool_calls) : "—"}
              color="text-orange-500"
            />
            <StatCard
              icon={DollarSign}
              label="Total Cost"
              value={summary ? `$${summary.total_cost_usd.toFixed(6)}` : "—"}
              color="text-green-500"
            />
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Recent Activity</CardTitle>
              </CardHeader>
              <CardContent className="max-h-80 overflow-y-auto">
                {activities.length === 0 ? (
                  <p className="text-muted-foreground text-sm">No activity yet</p>
                ) : (
                  <div className="space-y-2">
                    {activities.map((evt, i) => (
                      <div key={i} className="flex items-start gap-2 text-sm">
                        {statusIcon(evt.event_type)}
                        <div className="flex-1 min-w-0">
                          <span className="font-medium">{evt.event_type}</span>
                          <span className="text-muted-foreground ml-1">
                            [{evt.session_id?.slice(0, 8)}]
                          </span>
                          <p className="text-muted-foreground truncate">
                            {JSON.stringify(evt.data)}
                          </p>
                        </div>
                        <span className="text-muted-foreground shrink-0 text-xs">
                          {formatTime(evt.timestamp)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Active Sessions</CardTitle>
              </CardHeader>
              <CardContent className="max-h-80 overflow-y-auto">
                {sessions.length === 0 ? (
                  <p className="text-muted-foreground text-sm">No active sessions</p>
                ) : (
                  <div className="space-y-2">
                    {sessions.map((s) => (
                      <div key={s.session_id} className="flex items-center justify-between text-sm">
                        <div className="flex items-center gap-2">
                          {statusIcon(s.status)}
                          <span className="font-mono text-xs">
                            {s.session_id?.slice(0, 12)}
                          </span>
                        </div>
                        <span className="text-muted-foreground">
                          {s.tool_calls} calls · ${s.cost_usd.toFixed(6)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}

      {activeTab === "sessions" && (
        <Card>
          <CardHeader>
            <CardTitle>All Sessions</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {sessions.length === 0 ? (
                <p className="text-muted-foreground text-sm">No sessions</p>
              ) : (
                sessions.map((s) => (
                  <div
                    key={s.session_id}
                    className="flex items-center justify-between rounded border p-3 text-sm"
                  >
                    <div className="flex items-center gap-3">
                      {statusIcon(s.status)}
                      <div>
                        <p className="font-mono text-xs font-medium">{s.session_id}</p>
                        <p className="text-muted-foreground text-xs">
                          Started {formatTime(s.started_at)}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <span>{s.tool_calls} tool calls</span>
                      <span>{formatDuration(s.total_duration_ms)}</span>
                      <span>${s.cost_usd.toFixed(6)}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {activeTab === "tools" && (
        <Card>
          <CardHeader>
            <CardTitle>Tool Call Log</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {toolCalls.length === 0 ? (
                <p className="text-muted-foreground text-sm">No tool calls recorded</p>
              ) : (
                toolCalls.map((tc, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between rounded px-2 py-1.5 text-sm even:bg-muted/50"
                  >
                    <div className="flex items-center gap-2">
                      {tc.status === "error" ? (
                        <AlertCircle className="h-3.5 w-3.5 text-red-500" />
                      ) : (
                        <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
                      )}
                      <span className="font-mono text-xs font-medium">{tc.tool_name}</span>
                      <span className="text-muted-foreground text-xs">
                        [{tc.session_id?.slice(0, 8)}]
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      <span>{formatDuration(tc.duration_ms)}</span>
                      {tc.cost_usd > 0 && <span>${tc.cost_usd.toFixed(6)}</span>}
                      <span>{formatTime(tc.timestamp)}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
