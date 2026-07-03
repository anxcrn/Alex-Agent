import { useEffect, useRef, useState, useCallback } from "react";
import { 
  Send, 
  Bot, 
  User, 
  Sparkles, 
  Terminal, 
  Cpu,
  ChevronDown, 
  ChevronUp, 
  AlertTriangle,
  Loader
} from "lucide-react";
import { Markdown } from "@/components/Markdown";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { api, buildWsAuthParam, ALEX_BASE_PATH } from "@/lib/api";
import { cn } from "@/lib/utils";
import "./ChatGPTStyleChat.css";

interface Message {
  role: "user" | "assistant" | "system";
  content: string;
  id?: string;
  timestamp?: number;
  thinking?: string;
  toolCalls?: { name: string; args?: string; id?: string }[];
}

interface PendingDialog {
  id: string;
  type: "approval" | "question";
  command?: string;
  description?: string;
  text?: string;
  options?: string[];
}

interface ChatGPTStyleChatProps {
  sessionId: string | null;
  profile?: string;
}

export function ChatGPTStyleChat({ sessionId, profile }: ChatGPTStyleChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState("");
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [currentThinking, setCurrentThinking] = useState("");
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [pendingDialog, setPendingDialog] = useState<PendingDialog | null>(null);
  const [activeModel, setActiveModel] = useState<string>("");
  const [connectionState, setConnectionState] = useState<"connecting" | "live" | "offline">("connecting");
  const [isThinkingExpanded, setIsThinkingExpanded] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const messageIdCounterRef = useRef(0);

  // Load session messages from DB
  const loadMessages = useCallback(async () => {
    if (!sessionId) {
      setMessages([]);
      return;
    }
    setLoading(true);
    try {
      const data = await api.getSessionMessages(sessionId);
      if (data && Array.isArray(data.messages)) {
        // Map messages to our Message structure
        const mapped: Message[] = data.messages.map((m: any) => ({
          role: m.role,
          content: typeof m.content === "string" ? m.content : JSON.stringify(m.content),
          id: `msg-${messageIdCounterRef.current++}`,
        }));
        setMessages(mapped);
      }
    } catch (err) {
      console.error("Failed to load session messages:", err);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  // Load model info
  const loadModelInfo = useCallback(async () => {
    try {
      const info = await api.getModelInfo();
      if (info?.model) {
        setActiveModel(String(info.model));
      }
    } catch (err) {
      console.error("Failed to fetch model info:", err);
    }
  }, []);

  useEffect(() => {
    void loadMessages();
    void loadModelInfo();
  }, [loadMessages, loadModelInfo]);

  // Scroll to bottom
  const scrollToBottom = useCallback(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, currentThinking, activeTool, scrollToBottom]);

  // Initialize and connect WebSocket
  useEffect(() => {
    if (!sessionId) return;

    let unmounting = false;
    let ws: WebSocket | null = null;

    const connectWs = async () => {
      setConnectionState("connecting");
      try {
        const [authName, authValue] = await buildWsAuthParam();
        if (unmounting) return;

        const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
        const qs = new URLSearchParams({ 
          [authName]: authValue,
          channel: `web-chat-${sessionId}`,
          profile: profile || ""
        });
        
        ws = new WebSocket(
          `${proto}//${window.location.host}${ALEX_BASE_PATH}/api/ws?${qs.toString()}`
        );
        wsRef.current = ws;

        ws.onopen = () => {
          if (unmounting) return;
          setConnectionState("live");
          // Resume session on the WebSocket server
          ws?.send(
            JSON.stringify({
              jsonrpc: "2.0",
              id: 1,
              method: "session.resume",
              params: {
                session_id: sessionId,
                cols: 80,
                profile: profile || ""
              }
            })
          );
        };

        ws.onmessage = (event) => {
          if (unmounting) return;
          try {
            const frame = JSON.parse(event.data);
            if (frame.method === "event" && frame.params) {
              const { type, payload } = frame.params;
              
              if (type === "message.start") {
                setStreaming(true);
                setCurrentThinking("");
                setActiveTool(null);
                setMessages((prev) => [
                  ...prev,
                  { role: "assistant", content: "", id: `msg-${messageIdCounterRef.current++}` }
                ]);
              } else if (type === "message.delta") {
                const deltaText = payload?.text || "";
                setMessages((prev) => {
                  if (prev.length === 0) return prev;
                  const next = [...prev];
                  const last = next[next.length - 1];
                  if (last.role === "assistant") {
                    last.content += deltaText;
                  }
                  return next;
                });
              } else if (type === "status.update") {
                const kind = payload?.kind;
                const text = payload?.text || "";
                
                if (kind === "thinking") {
                  setCurrentThinking((prev) => prev + text);
                } else if (kind === "tool_start" || kind === "status") {
                  setActiveTool(text);
                }
              } else if (type === "message.complete") {
                setStreaming(false);
                setCurrentThinking("");
                setActiveTool(null);
                // Trigger reload of messages to align with DB state
                void loadMessages();
              } else if (type === "approval.request" || type === "dialog.request") {
                setPendingDialog({
                  id: payload?.id,
                  type: payload?.type || "approval",
                  command: payload?.command,
                  description: payload?.description,
                  text: payload?.text,
                  options: payload?.options
                });
              }
            }
          } catch (err) {
            console.error("Failed to parse WebSocket frame:", err);
          }
        };

        ws.onclose = () => {
          if (unmounting) return;
          setConnectionState("offline");
          // Reconnect logic
          setTimeout(() => {
            if (!unmounting) connectWs();
          }, 3000);
        };

        ws.onerror = () => {
          if (unmounting) return;
          setConnectionState("offline");
        };

      } catch (err) {
        console.error("WebSocket connection setup failed:", err);
        setConnectionState("offline");
      }
    };

    void connectWs();

    return () => {
      unmounting = true;
      if (ws) ws.close();
      wsRef.current = null;
    };
  }, [sessionId, profile, loadMessages]);

  const handleSend = () => {
    if (!inputText.trim() || !sessionId || connectionState !== "live" || streaming) return;

    const userMsg: Message = {
      role: "user",
      content: inputText,
      id: `msg-${messageIdCounterRef.current++}`
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputText("");

    wsRef.current?.send(
      JSON.stringify({
        jsonrpc: "2.0",
        id: messageIdCounterRef.current++,
        method: "prompt.submit",
        params: {
          session_id: sessionId,
          text: userMsg.content
        }
      })
    );
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const resolveDialog = (approved: boolean, responseText?: string) => {
    if (!pendingDialog) return;
    
    // Resolve via HTTP endpoint
    const body = pendingDialog.type === "question" 
      ? { answer: responseText || "" } 
      : { granted: approved };

    fetch(`/api/v1/dialogs/${pendingDialog.id}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    })
      .then((res) => {
        if (res.ok) {
          setPendingDialog(null);
        }
      })
      .catch((err) => {
        console.error("Failed to resolve dialog:", err);
      });
  };

  return (
    <div className="flex flex-col flex-1 h-full min-h-0 relative chat-container-style">
      {/* Top Header info */}
      <div className="shrink-0 flex items-center justify-between border-b border-white/5 pb-4 mb-4">
        <div className="flex items-center gap-2">
          <Sparkles className="size-4 text-[#BF5FFF] animate-pulse" />
          <span className="text-xs font-mono tracking-wider text-white/50 uppercase">
            Model: <span className="text-[#00F0FF]">{activeModel || "Loading..."}</span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className={cn(
            "size-2 rounded-full",
            connectionState === "live" ? "bg-green-500 animate-pulse" : 
            connectionState === "connecting" ? "bg-yellow-500" : "bg-red-500"
          )} />
          <span className="text-[10px] uppercase font-mono tracking-widest text-white/40">
            {connectionState}
          </span>
        </div>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto pr-2 space-y-6 min-h-0 chat-scrollbar">
        {loading ? (
          <div className="flex h-40 items-center justify-center">
            <Spinner className="size-6 text-[#BF5FFF]" />
          </div>
        ) : messages.length === 0 ? (
          <div className="flex h-[50vh] flex-col items-center justify-center text-center gap-4">
            <div className="size-16 rounded-full border border-white/5 bg-white/[0.02] flex items-center justify-center text-2xl">
              👋
            </div>
            <div className="space-y-1">
              <h3 className="font-bold text-white tracking-wide">How can I help you today?</h3>
              <p className="text-xs text-white/40 max-w-sm">
                Ask a question, start coding, or instruct me to build a new feature.
              </p>
            </div>
          </div>
        ) : (
          messages.map((msg) => (
            <div 
              key={msg.id} 
              className={cn(
                "flex gap-4 max-w-4xl",
                msg.role === "user" ? "ml-auto flex-row-reverse" : "mr-auto"
              )}
            >
              {/* Avatar */}
              <div className={cn(
                "size-8 rounded-sm flex items-center justify-center shrink-0 border",
                msg.role === "user" 
                  ? "border-[#BF5FFF]/30 bg-[#BF5FFF]/10 text-[#BF5FFF]" 
                  : "border-[#00F0FF]/30 bg-[#00F0FF]/10 text-[#00F0FF]"
              )}>
                {msg.role === "user" ? <User className="size-4" /> : <Bot className="size-4" />}
              </div>

              {/* Bubble */}
              <div className="space-y-2 max-w-[85%]">
                <div className={cn(
                  "rounded-lg px-4 py-3 text-sm leading-relaxed relative border",
                  msg.role === "user" 
                    ? "bg-[#BF5FFF]/5 border-[#BF5FFF]/20 text-white rounded-tr-none shadow-md shadow-[#BF5FFF]/5" 
                    : "bg-white/[0.01] border-white/5 text-white/90 rounded-tl-none"
                )}>
                  <Markdown content={msg.content} />
                </div>
              </div>
            </div>
          ))
        )}

        {/* Live streaming status updates */}
        {streaming && (currentThinking || activeTool) && (
          <div className="flex gap-4 max-w-4xl mr-auto">
            <div className="size-8 rounded-sm flex items-center justify-center shrink-0 border border-[#00F0FF]/30 bg-[#00F0FF]/10 text-[#00F0FF]">
              <Loader className="size-4 animate-spin" />
            </div>

            <div className="space-y-3 flex-1 min-w-0">
              {/* Thinking block */}
              {currentThinking && (
                <div className="border border-white/5 bg-white/[0.01] rounded-lg overflow-hidden">
                  <button 
                    onClick={() => setIsThinkingExpanded(!isThinkingExpanded)}
                    className="w-full flex items-center justify-between px-3 py-2 text-xs text-white/40 hover:text-white/60 hover:bg-white/[0.02] transition-colors"
                  >
                    <span className="flex items-center gap-2">
                      <Cpu className="size-3.5 animate-pulse text-[#BF5FFF]" />
                      Thinking Process...
                    </span>
                    {isThinkingExpanded ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
                  </button>
                  {isThinkingExpanded && (
                    <div className="px-3 pb-3 pt-1 text-xs font-mono text-white/50 border-t border-white/5 bg-black/30 max-h-40 overflow-y-auto whitespace-pre-wrap">
                      {currentThinking}
                    </div>
                  )}
                </div>
              )}

              {/* Tool activity pill */}
              {activeTool && (
                <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-[#00F0FF]/20 bg-[#00F0FF]/5 text-xs text-[#00F0FF]">
                  <Terminal className="size-3.5 animate-spin" />
                  <span>{activeTool}</span>
                </div>
              )}
            </div>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* Dialog approval card */}
      {pendingDialog && (
        <div className="absolute inset-x-0 bottom-24 mx-auto max-w-lg z-50 border border-[#FF007F]/40 bg-black/90 p-5 rounded-lg shadow-2xl backdrop-blur-md space-y-4 animate-in fade-in slide-in-from-bottom-4">
          <div className="flex items-start gap-3">
            <div className="size-10 rounded-full border border-[#FF007F]/30 bg-[#FF007F]/5 flex items-center justify-center text-[#FF007F] shrink-0">
              <AlertTriangle className="size-5" />
            </div>
            <div className="space-y-1 flex-1">
              <h4 className="text-sm font-bold uppercase tracking-wider text-white">
                {pendingDialog.type === "approval" ? "Tool Approval Required" : "User Confirmation"}
              </h4>
              <p className="text-xs text-white/60 leading-relaxed">
                {pendingDialog.description || "Confirm if you wish to allow this action."}
              </p>
            </div>
          </div>

          {pendingDialog.command && (
            <div className="bg-black/60 border border-white/10 rounded p-3 font-mono text-xs text-white/80 overflow-x-auto whitespace-pre">
              {pendingDialog.command}
            </div>
          )}

          <div className="flex gap-3 justify-end pt-2">
            <button
              onClick={() => resolveDialog(false)}
              className="px-4 py-2 text-xs font-bold uppercase tracking-wider bg-white/5 border border-white/10 hover:bg-white/10 text-white rounded-sm transition-all"
            >
              Deny
            </button>
            <button
              onClick={() => resolveDialog(true)}
              className="px-4 py-2 text-xs font-bold uppercase tracking-wider bg-[#FF007F]/20 border border-[#FF007F]/50 hover:bg-[#FF007F] text-white rounded-sm transition-all"
            >
              Approve
            </button>
          </div>
        </div>
      )}

      {/* Input prompt area */}
      <div className="shrink-0 pt-4 relative">
        <div className="relative flex items-end border border-white/10 rounded-lg bg-white/[0.02] p-2 focus-within:border-white/20 transition-all">
          <textarea
            ref={inputRef}
            rows={1}
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={connectionState !== "live" || streaming}
            placeholder={
              connectionState !== "live" ? "Reconnecting to backend..." : 
              streaming ? "Alex is thinking..." : "Message Alex Agent..."
            }
            className="flex-1 max-h-40 bg-transparent text-sm text-white/90 placeholder:text-white/30 resize-none outline-none border-none pl-2 py-2 pr-12 min-h-[36px]"
            style={{ height: "auto" }}
          />

          <button
            onClick={handleSend}
            disabled={!inputText.trim() || connectionState !== "live" || streaming}
            className="absolute right-3 bottom-3 size-8 flex items-center justify-center rounded-sm bg-[#BF5FFF]/20 border border-[#BF5FFF]/50 hover:bg-[#BF5FFF] disabled:opacity-30 disabled:hover:bg-[#BF5FFF]/20 text-white transition-all duration-300"
          >
            <Send className="size-4" />
          </button>
        </div>
        <div className="text-[10px] text-white/25 text-center mt-2 font-mono">
          Press Enter to send, Shift+Enter for new line. Designed by Charan Vankudoth.
        </div>
      </div>
    </div>
  );
}
