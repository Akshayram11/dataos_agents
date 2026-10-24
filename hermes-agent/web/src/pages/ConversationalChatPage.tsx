import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  ArrowDown,
  Bot,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleDot,
  File,
  Folder,
  FolderOpen,
  History,
  LoaderCircle,
  MessageSquarePlus,
  PanelRightClose,
  PanelRightOpen,
  Pencil,
  RefreshCw,
  Send,
  Square,
  Terminal,
  User,
  X,
  XCircle,
} from "lucide-react";
import type {
  GatewayEvent,
  ServerRequest,
  SessionCreateResult,
  SessionResumeResult,
  ToolCompletePayload,
  ToolProgressPayload,
  ToolStartPayload,
  TranscriptMessage,
} from "@hermes/shared";
import { Markdown } from "@/components/Markdown";
import { ModelPickerDialog } from "@/components/ModelPickerDialog";
import { useProfileScope } from "@/contexts/useProfileScope";
import { api, type ManagedFileEntry, type ManagedFilesResponse, type SessionInfo } from "@/lib/api";
import { errorMessage } from "@/lib/api-error";
import { GatewayClient, type ConnectionState } from "@/lib/gatewayClient";
import { cn, timeAgo } from "@/lib/utils";

type ChatRole = "user" | "assistant" | "system";

interface ChatMessage {
  id: string;
  role: ChatRole;
  text: string;
  streaming?: boolean;
  error?: boolean;
}

interface ToolActivity {
  id: string;
  name: string;
  status: "running" | "done" | "failed";
  detail: string;
  output?: string;
  progress?: string;
  duration?: number;
  startedAt: number;
}

interface PendingRequest {
  id: string;
  method: string;
  title: string;
  description: string;
  choices: string[];
  respond: (result: Record<string, unknown>) => void;
}

type RightTab = "cli" | "files" | "details";

const STARTERS = [
  "List running services in the engineering tenant",
  "Check failed DataOS resources and explain the likely cause",
  "Help me design a new DataOS agent",
  "Review the current repository workspace",
];

function textOf(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function redact(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(redact);
  if (!value || typeof value !== "object") return value;
  const result: Record<string, unknown> = {};
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    result[key] = /(token|secret|password|api.?key|authorization|credential)/i.test(key)
      ? "••••••••"
      : redact(child);
  }
  return result;
}

function summarizeArgs(value: unknown): string {
  if (!value || typeof value !== "object") return textOf(value);
  const safe = redact(value);
  const record = safe as Record<string, unknown>;
  for (const key of ["command", "cmd", "query", "path", "url", "resource", "name"]) {
    if (typeof record[key] === "string" && record[key]) return String(record[key]);
  }
  const rendered = textOf(safe);
  return rendered.length > 520 ? `${rendered.slice(0, 520)}…` : rendered;
}

function comparableAssistantText(value: string): string {
  return value
    .replace(/[`*_#>|]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function newerAssistantSupersedes(older: string, newer: string): boolean {
  const previous = comparableAssistantText(older);
  const next = comparableAssistantText(newer);
  return previous.length >= 80 && next.length > previous.length && next.startsWith(previous);
}

function collapseAssistantPrefixes(messages: ChatMessage[]): ChatMessage[] {
  return messages.reduce<ChatMessage[]>((result, message) => {
    const previous = result.at(-1);
    if (
      previous?.role === "assistant" &&
      message.role === "assistant" &&
      newerAssistantSupersedes(previous.text, message.text)
    ) {
      result[result.length - 1] = message;
    } else {
      result.push(message);
    }
    return result;
  }, []);
}

function transcriptToMessages(rows: TranscriptMessage[]): ChatMessage[] {
  return collapseAssistantPrefixes(rows.flatMap((row, index) => {
    if (row.role !== "user" && row.role !== "assistant" && row.role !== "system") return [];
    const text = textOf(row.text ?? row.content);
    if (!text.trim() || row.display_kind === "hidden") return [];
    return [{
      id: `history-${row.row_id ?? index}`,
      role: row.role,
      text,
    } as ChatMessage];
  }));
}

function eventForSession(event: GatewayEvent, sessionId: string | null): boolean {
  return !sessionId || !event.session_id || event.session_id === sessionId;
}

export default function ConversationalChatPage({ isActive = true }: { isActive?: boolean }) {
  const { profile } = useProfileScope();
  const gateway = useMemo(() => new GatewayClient(), []);
  const [connection, setConnection] = useState<ConnectionState>("idle");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [storedSessionId, setStoredSessionId] = useState<string | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activities, setActivities] = useState<ToolActivity[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [booting, setBooting] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sessionInfo, setSessionInfo] = useState<Record<string, unknown>>({});
  const [pendingRequest, setPendingRequest] = useState<PendingRequest | null>(null);
  const [rightTab, setRightTab] = useState<RightTab>("cli");
  const [rightOpen, setRightOpen] = useState(true);
  const [mobileRightOpen, setMobileRightOpen] = useState(false);
  const endRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const activeAssistantRef = useRef<string | null>(null);

  const finishOrphanedActivities = useCallback((status: "done" | "failed") => {
    const finishedAt = Date.now();
    setActivities((current) => current.map((item) =>
      item.status === "running"
        ? {
            ...item,
            status,
            duration: Math.max(0, (finishedAt - item.startedAt) / 1000),
            progress: undefined,
          }
        : item,
    ));
  }, []);

  const appendDelta = useCallback((text: string) => {
    if (!text) return;
    setMessages((current) => {
      const activeId = activeAssistantRef.current;
      if (activeId) {
        return current.map((message) =>
          message.id === activeId ? { ...message, text: message.text + text, streaming: true } : message,
        );
      }
      const id = `assistant-${crypto.randomUUID()}`;
      activeAssistantRef.current = id;
      return [...current, { id, role: "assistant", text, streaming: true }];
    });
  }, []);

  const completeAssistant = useCallback((payload: Record<string, unknown>) => {
    const finalText = textOf(payload.text);
    const finalError = textOf(payload.error || payload.failure_reason);
    setMessages((current) => {
      const activeId = activeAssistantRef.current;
      if (activeId) {
        return collapseAssistantPrefixes(current.map((message) =>
          message.id === activeId
            ? {
                ...message,
                text: finalText || message.text || finalError || "The turn ended without a response.",
                streaming: false,
                error: Boolean(finalError),
              }
            : message,
        ));
      }
      if (!finalText && !finalError) return current;
      return collapseAssistantPrefixes([...current, {
        id: `assistant-${crypto.randomUUID()}`,
        role: "assistant",
        text: finalText || finalError,
        error: Boolean(finalError),
      }]);
    });
    activeAssistantRef.current = null;
    setBusy(false);
  }, []);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    const offState = gateway.onState(setConnection);
    const offAny = gateway.onAny((event) => {
      if (!eventForSession(event, sessionIdRef.current)) return;
      const payload = (event.payload ?? {}) as Record<string, unknown>;

      if (event.type === "message.start") {
        // A missing tool.complete frame must not leave an earlier turn looking
        // permanently busy. The agent cannot start the next assistant message
        // while a synchronous tool call from the previous turn is still live.
        finishOrphanedActivities("done");
        const id = `assistant-${crypto.randomUUID()}`;
        activeAssistantRef.current = id;
        setMessages((current) => [...current, { id, role: "assistant", text: "", streaming: true }]);
        setBusy(true);
      } else if (event.type === "message.delta") {
        if (payload.text === null || payload.text === undefined) {
          const activeId = activeAssistantRef.current;
          if (activeId) {
            setMessages((current) => current.map((message) =>
              message.id === activeId ? { ...message, streaming: false } : message,
            ));
            activeAssistantRef.current = null;
          }
        } else {
          appendDelta(textOf(payload.text));
        }
      } else if (event.type === "message.interim") {
        const interimText = textOf(payload.text);
        const activeId = activeAssistantRef.current;
        setMessages((current) => {
          if (activeId) {
            return current.map((message) =>
              message.id === activeId
                ? {
                    ...message,
                    text: payload.already_streamed ? message.text : (message.text || interimText),
                    streaming: false,
                  }
                : message,
            );
          }
          if (!interimText || payload.already_streamed) return current;
          return [...current, {
            id: `assistant-${crypto.randomUUID()}`,
            role: "assistant" as const,
            text: interimText,
          }];
        });
        activeAssistantRef.current = null;
      } else if (event.type === "message.complete") {
        completeAssistant(payload);
        // Some MCP/tool bridges can finish the turn without forwarding their
        // terminal tool.complete frame. message.complete is the authoritative
        // turn boundary, so reconcile any orphaned spinner here.
        finishOrphanedActivities("done");
      } else if (event.type === "error") {
        const message = textOf(payload.message) || "The agent reported an error.";
        setError(message);
        setBusy(false);
        finishOrphanedActivities("failed");
      } else if (event.type === "session.info") {
        setSessionInfo((current) => ({ ...current, ...payload }));
      } else if (event.type === "tool.start") {
        const tool = payload as unknown as ToolStartPayload;
        setActivities((current) => [{
          id: tool.tool_id,
          name: tool.name,
          status: "running" as const,
          detail: summarizeArgs(tool.args ?? tool.args_text ?? tool.context ?? ""),
          startedAt: Date.now(),
        }, ...current.filter((item) => item.id !== tool.tool_id)].slice(0, 80));
      } else if (event.type === "tool.progress") {
        const tool = payload as unknown as ToolProgressPayload;
        setActivities((current) => current.map((item) =>
          item.id === tool.tool_id
            ? { ...item, progress: tool.message || (tool.percent != null ? `${Math.round(tool.percent)}%` : "Working…") }
            : item,
        ));
      } else if (event.type === "tool.complete") {
        const tool = payload as unknown as ToolCompletePayload;
        const output = textOf(tool.result_text ?? tool.summary ?? tool.result);
        setActivities((current) => current.map((item) =>
          item.id === tool.tool_id
            ? {
                ...item,
                status: tool.is_error ? "failed" : "done",
                output: output.length > 4000 ? `${output.slice(0, 4000)}\n…` : output,
                duration: tool.duration_s ?? undefined,
                progress: undefined,
              }
            : item,
        ));
      }
    });

    const offRequest = gateway.onRequest((request: ServerRequest) => {
      const params = request.params as Record<string, unknown>;
      if (params.session_id && params.session_id !== sessionIdRef.current) return false;
      const choices = Array.isArray(params.choices)
        ? params.choices.map(String)
        : request.method === "approval" ? ["once", "session", "deny"] : ["Submit", "Skip"];
      setPendingRequest({
        id: request.id,
        method: request.method,
        title: request.method === "approval" ? "Approval required" : "Agent needs your input",
        description: textOf(params.description || params.command || params.question || params.prompt),
        choices,
        respond: request.respond,
      });
      return true;
    });

    return () => {
      offState();
      offAny();
      offRequest();
    };
  }, [appendDelta, completeAssistant, finishOrphanedActivities, gateway]);

  const createSession = useCallback(async (clear = false) => {
    setBooting(true);
    setError(null);
    setBusy(false);
    activeAssistantRef.current = null;
    if (clear) {
      setMessages([]);
      setActivities([]);
    }
    try {
      if (gateway.connectionState !== "open") await gateway.connect();
      const result = await gateway.request<SessionCreateResult>("session.create", {
        close_on_disconnect: false,
        follow_profile_config: true,
        source: "tool",
        title: "DataOS workspace",
        ...(profile ? { profile } : {}),
      });
      sessionIdRef.current = result.session_id;
      setSessionId(result.session_id);
      setStoredSessionId(result.stored_session_id);
      setSessionInfo(result.info as unknown as Record<string, unknown>);
      setMessages(transcriptToMessages(result.messages));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBooting(false);
    }
  }, [gateway, profile]);

  const resumeSession = useCallback(async (targetSessionId: string) => {
    if (!targetSessionId || busy || targetSessionId === storedSessionId) return;
    setBooting(true);
    setError(null);
    activeAssistantRef.current = null;
    const previousRuntimeId = sessionIdRef.current;
    try {
      if (gateway.connectionState !== "open") await gateway.connect();
      const result = await gateway.request<SessionResumeResult>("session.resume", {
        session_id: targetSessionId,
        close_on_disconnect: false,
        source: "tool",
        inline_images: false,
        ...(profile ? { profile } : {}),
      });
      sessionIdRef.current = result.session_id;
      setSessionId(result.session_id);
      setStoredSessionId(result.stored_session_id || result.session_key || result.resumed || targetSessionId);
      setSessionInfo(result.info as unknown as Record<string, unknown>);
      setMessages(transcriptToMessages(result.messages));
      setActivities([]);
      setBusy(Boolean(result.running));
      if (previousRuntimeId && previousRuntimeId !== result.session_id) {
        void gateway.request("session.close", { session_id: previousRuntimeId }).catch(() => undefined);
      }
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBooting(false);
    }
  }, [busy, gateway, profile, storedSessionId]);

  useEffect(() => {
    void createSession(true);
    return () => gateway.close();
  }, [createSession, gateway]);

  useEffect(() => {
    if (isActive) inputRef.current?.focus();
  }, [isActive]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const text = input.trim();
    if (!text || !sessionId || connection !== "open") return;
    setInput("");
    setError(null);
    setMessages((current) => [...current, {
      id: `user-${crypto.randomUUID()}`,
      role: "user",
      text,
    }]);
    setBusy(true);
    try {
      await gateway.request("prompt.submit", {
        session_id: sessionId,
        text,
        title_preview: text.slice(0, 72),
        surface: "dashboard",
        ...(profile ? { profile } : {}),
      });
    } catch (reason) {
      setBusy(false);
      setError(errorMessage(reason));
    }
  };

  const interrupt = async () => {
    if (!sessionId) return;
    try {
      await gateway.request("session.interrupt", {
        session_id: sessionId,
        ...(profile ? { profile } : {}),
      });
    } finally {
      setBusy(false);
    }
  };

  const answerRequest = (choice: string) => {
    if (!pendingRequest) return;
    const key = pendingRequest.method === "approval" ? "choice" : "value";
    pendingRequest.respond({ [key]: choice });
    setPendingRequest(null);
  };

  const activitySummary = activities.length
    ? `${activities.filter((item) => item.status === "running").length} running · ${activities.length} events`
    : "Waiting for agent activity";

  return (
    <div className="relative flex min-h-0 flex-1 overflow-hidden rounded-t-xl border border-current/15 bg-background-base shadow-[0_16px_70px_rgba(0,0,0,0.18)]">
      <main className="flex min-w-0 flex-1 flex-col bg-[radial-gradient(circle_at_top_left,var(--background-secondary),transparent_42%)]">
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-current/10 px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-midground text-background-base">
              <Bot className="h-5 w-5" />
            </span>
            <div className="min-w-0">
              <h1 className="truncate text-base font-bold text-midground">{profile || "Botsky Agent"}</h1>
              <p className="flex items-center gap-1.5 truncate text-xs text-text-tertiary">
                <span className={cn("h-1.5 w-1.5 rounded-full", connection === "open" ? "bg-emerald-400" : "bg-amber-400")} />
                {connection === "open" ? "Connected to DataOS workspace" : "Connecting to agent"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void createSession(true)}
              className="hidden items-center gap-2 rounded-md border border-current/15 px-3 py-2 text-xs font-semibold text-text-secondary hover:text-midground sm:flex"
            >
              <MessageSquarePlus className="h-4 w-4" /> New chat
            </button>
            <button
              type="button"
              onClick={() => setMobileRightOpen(true)}
              className="flex h-9 w-9 items-center justify-center rounded-md border border-current/15 text-text-secondary hover:text-midground xl:hidden"
              aria-label="Open workspace panel"
            >
              <Terminal className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setRightOpen((value) => !value)}
              className="hidden h-9 w-9 items-center justify-center rounded-md border border-current/15 text-text-secondary hover:text-midground xl:flex"
              aria-label={rightOpen ? "Hide workspace panel" : "Show workspace panel"}
            >
              {rightOpen ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}
            </button>
          </div>
        </header>

        <section className="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-8 lg:px-12">
          <div className="mx-auto flex min-h-full max-w-3xl flex-col">
            {booting ? (
              <div className="flex flex-1 items-center justify-center gap-2 text-sm text-text-tertiary">
                <LoaderCircle className="h-4 w-4 animate-spin" /> Starting your DataOS agent…
              </div>
            ) : messages.length === 0 ? (
              <div className="flex flex-1 flex-col justify-center py-10">
                <div className="mb-8 max-w-2xl">
                  <span className="mb-4 inline-flex items-center gap-2 rounded-full border border-midground/25 bg-midground/5 px-3 py-1 text-xs font-semibold text-midground">
                    <CircleDot className="h-3 w-3" /> DataOS-native teammate
                  </span>
                  <h2 className="text-3xl font-bold leading-tight text-midground sm:text-4xl">
                    What should we build or operate today?
                  </h2>
                  <p className="mt-3 max-w-xl text-sm leading-relaxed text-text-secondary">
                    Ask in plain language. The agent can use its DataOS CLI, connected MCPs, skills, repository workspace and Python runtime while you watch the work live.
                  </p>
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  {STARTERS.map((starter) => (
                    <button
                      key={starter}
                      type="button"
                      onClick={() => setInput(starter)}
                      className="group flex min-h-20 items-center justify-between rounded-lg border border-current/15 bg-background-base/70 p-4 text-left text-sm font-medium text-text-secondary transition hover:border-midground/50 hover:text-midground"
                    >
                      <span>{starter}</span>
                      <ChevronRight className="h-4 w-4 shrink-0 opacity-40 transition-transform group-hover:translate-x-0.5 group-hover:opacity-100" />
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="space-y-7 pb-8">
                {messages.map((message) => (
                  <article key={message.id} className={cn("flex gap-3", message.role === "user" && "justify-end")}>
                    {message.role !== "user" && (
                      <span className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-current/15 bg-background-secondary text-midground">
                        <Bot className="h-3.5 w-3.5" />
                      </span>
                    )}
                    <div className={cn(
                      "max-w-[88%]",
                      message.role === "user"
                        ? "rounded-2xl rounded-br-sm bg-midground px-4 py-3 text-background-base"
                        : "min-w-0 rounded-xl border border-current/10 bg-background-base/75 px-4 py-3 shadow-sm",
                      message.error && "border-red-500/40 text-red-400",
                    )}>
                      {message.role === "user" ? (
                        <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.text}</p>
                      ) : (
                        <Markdown content={message.text} streaming={message.streaming} />
                      )}
                    </div>
                    {message.role === "user" && (
                      <span className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-current/15 text-text-secondary">
                        <User className="h-3.5 w-3.5" />
                      </span>
                    )}
                  </article>
                ))}
                <div ref={endRef} />
              </div>
            )}
          </div>
        </section>

        {error && (
          <div className="mx-4 mb-2 flex items-start justify-between gap-3 rounded-md border border-red-500/35 bg-red-500/5 px-3 py-2 text-xs text-red-400 sm:mx-8 lg:mx-12">
            <span>{error}</span>
            <button type="button" onClick={() => setError(null)} aria-label="Dismiss error"><X className="h-3.5 w-3.5" /></button>
          </div>
        )}

        <div className="shrink-0 px-4 pb-4 sm:px-8 sm:pb-6 lg:px-12">
          <form onSubmit={submit} className="mx-auto max-w-3xl rounded-2xl border border-current/20 bg-background-base p-2 shadow-[0_12px_40px_rgba(0,0,0,0.2)] focus-within:border-midground/55">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void submit();
                }
              }}
              rows={2}
              placeholder={`Message ${profile || "Botsky"}…`}
              className="max-h-40 min-h-14 w-full resize-none bg-transparent px-3 py-2 text-sm text-midground outline-none placeholder:text-text-tertiary"
            />
            <div className="flex items-center justify-between px-2 pb-1">
              <span className="text-[0.68rem] text-text-tertiary">Enter to send · Shift + Enter for a new line</span>
              {busy ? (
                <button
                  type="button"
                  onClick={() => void interrupt()}
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-red-500 text-white hover:bg-red-400"
                  aria-label="Stop response"
                >
                  <Square className="h-3.5 w-3.5 fill-current" />
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!input.trim() || !sessionId || connection !== "open"}
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-midground text-background-base disabled:cursor-not-allowed disabled:opacity-35"
                  aria-label="Send message"
                >
                  <Send className="h-4 w-4" />
                </button>
              )}
            </div>
          </form>
        </div>
      </main>

      {rightOpen && (
        <WorkspacePanel
          className="hidden w-[min(38vw,34rem)] shrink-0 border-l border-current/15 xl:flex"
          tab={rightTab}
          setTab={setRightTab}
          activities={activities}
          activitySummary={activitySummary}
          sessionInfo={sessionInfo}
          profile={profile}
          storedSessionId={storedSessionId}
          onOpenChat={resumeSession}
          chatBusy={busy || booting}
          onModelChanged={() => void createSession(true)}
        />
      )}

      {mobileRightOpen && (
        <div className="absolute inset-0 z-30 flex justify-end bg-black/60 xl:hidden" onClick={() => setMobileRightOpen(false)}>
          <WorkspacePanel
            className="h-full w-[min(92vw,34rem)] border-l border-current/15 bg-background-base"
            tab={rightTab}
            setTab={setRightTab}
            activities={activities}
            activitySummary={activitySummary}
            sessionInfo={sessionInfo}
            profile={profile}
            storedSessionId={storedSessionId}
            onOpenChat={resumeSession}
            chatBusy={busy || booting}
            onModelChanged={() => void createSession(true)}
            onClose={() => setMobileRightOpen(false)}
            onClick={(event) => event.stopPropagation()}
          />
        </div>
      )}

      {pendingRequest && (
        <div className="absolute inset-0 z-40 flex items-center justify-center bg-black/65 p-4">
          <div className="w-full max-w-lg rounded-xl border border-current/20 bg-background-base p-5 shadow-2xl">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-amber-400">Human checkpoint</p>
            <h3 className="mt-2 text-xl font-bold text-midground">{pendingRequest.title}</h3>
            <pre className="mt-4 max-h-56 overflow-auto whitespace-pre-wrap rounded-lg border border-current/10 bg-background-secondary p-3 text-xs text-text-secondary">
              {pendingRequest.description || "Review this request before the agent continues."}
            </pre>
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              {pendingRequest.choices.map((choice) => (
                <button
                  key={choice}
                  type="button"
                  onClick={() => answerRequest(choice)}
                  className={cn(
                    "rounded-md border px-4 py-2 text-xs font-semibold capitalize",
                    /deny|skip|cancel/i.test(choice)
                      ? "border-current/20 text-text-secondary hover:text-midground"
                      : "border-midground bg-midground text-background-base",
                  )}
                >
                  {choice}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function WorkspacePanel({
  className,
  tab,
  setTab,
  activities,
  activitySummary,
  sessionInfo,
  profile,
  storedSessionId,
  onOpenChat,
  chatBusy,
  onModelChanged,
  onClose,
  onClick,
}: {
  className?: string;
  tab: RightTab;
  setTab: (tab: RightTab) => void;
  activities: ToolActivity[];
  activitySummary: string;
  sessionInfo: Record<string, unknown>;
  profile: string;
  storedSessionId: string | null;
  onOpenChat: (sessionId: string) => Promise<void>;
  chatBusy: boolean;
  onModelChanged: () => void;
  onClose?: () => void;
  onClick?: (event: React.MouseEvent<HTMLDivElement>) => void;
}) {
  return (
    <aside className={cn("min-h-0 flex-col bg-background-base", className)} onClick={onClick}>
      <header className="flex h-16 shrink-0 items-center justify-between border-b border-current/10 px-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-text-tertiary">Live workspace</p>
          <p className="mt-0.5 text-xs text-text-secondary">{activitySummary}</p>
        </div>
        {onClose && <button type="button" onClick={onClose} aria-label="Close workspace"><X className="h-4 w-4" /></button>}
      </header>
      <div className="grid shrink-0 grid-cols-3 border-b border-current/10">
        {(["cli", "files", "details"] as RightTab[]).map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setTab(item)}
            className={cn(
              "border-b-2 px-3 py-3 text-xs font-semibold uppercase tracking-[0.12em]",
              tab === item ? "border-midground text-midground" : "border-transparent text-text-tertiary hover:text-text-secondary",
            )}
          >
            {item === "cli" ? "CLI" : item === "files" ? "Files" : "Details"}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {tab === "cli" && <CliActivity activities={activities} />}
        {tab === "files" && <CompactFiles />}
        {tab === "details" && (
          <AgentDetails
            info={sessionInfo}
            profile={profile}
            storedSessionId={storedSessionId}
            onOpenChat={onOpenChat}
            chatBusy={chatBusy}
            onModelChanged={onModelChanged}
          />
        )}
      </div>
    </aside>
  );
}

function CliActivity({ activities }: { activities: ToolActivity[] }) {
  if (!activities.length) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-8 text-center">
        <Terminal className="h-8 w-8 text-text-tertiary" />
        <h3 className="mt-4 text-sm font-bold text-midground">CLI activity will appear here</h3>
        <p className="mt-2 max-w-xs text-xs leading-relaxed text-text-tertiary">
          DataOS CLI calls, MCP tools, shell commands and their results are shown as the agent works. Credentials are redacted.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2 p-3">
      {activities.map((activity) => (
        <details key={activity.id} open={activity.status === "running"} className="group rounded-lg border border-current/10 bg-black/20">
          <summary className="flex cursor-pointer list-none items-start gap-2.5 p-3">
            <span className="mt-0.5">
              {activity.status === "running" ? <LoaderCircle className="h-3.5 w-3.5 animate-spin text-amber-400" /> :
                activity.status === "done" ? <Check className="h-3.5 w-3.5 text-emerald-400" /> :
                  <XCircle className="h-3.5 w-3.5 text-red-400" />}
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-center justify-between gap-2">
                <span className="truncate font-mono text-xs font-semibold text-midground">{activity.name}</span>
                {activity.duration != null && <span className="shrink-0 text-[0.65rem] text-text-tertiary">{activity.duration.toFixed(1)}s</span>}
              </span>
              <span className="mt-1 block truncate font-mono text-[0.68rem] text-text-tertiary">{activity.progress || activity.detail || "Running tool"}</span>
            </span>
            <ArrowDown className="mt-0.5 h-3.5 w-3.5 text-text-tertiary transition-transform group-open:rotate-180" />
          </summary>
          <div className="border-t border-current/10 p-3">
            {activity.detail && <pre className="whitespace-pre-wrap break-all font-mono text-[0.68rem] leading-relaxed text-amber-200/80">$ {activity.detail}</pre>}
            {activity.output && <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap break-words border-l border-current/15 pl-3 font-mono text-[0.68rem] leading-relaxed text-text-secondary">{activity.output}</pre>}
          </div>
        </details>
      ))}
    </div>
  );
}

function CompactFiles() {
  const [listing, setListing] = useState<ManagedFilesResponse | null>(null);
  const [path, setPath] = useState<string | undefined>();
  const [selected, setSelected] = useState<{ entry: ManagedFileEntry; preview?: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (next?: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.listFiles(next);
      setListing(result);
      setPath(result.path);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const open = async (entry: ManagedFileEntry) => {
    if (entry.is_directory) {
      setSelected(null);
      await load(entry.path);
      return;
    }
    setSelected({ entry });
    if (entry.size != null && entry.size > 512_000) return;
    if (entry.mime_type && !/^(text\/|application\/(json|yaml|xml|javascript))/.test(entry.mime_type)) return;
    try {
      const result = await api.readFile(entry.path);
      const comma = result.data_url.indexOf(",");
      if (comma < 0) return;
      const meta = result.data_url.slice(0, comma);
      const raw = result.data_url.slice(comma + 1);
      const preview = meta.includes(";base64")
        ? decodeURIComponent(Array.from(atob(raw), (char) => `%${char.charCodeAt(0).toString(16).padStart(2, "0")}`).join(""))
        : decodeURIComponent(raw);
      setSelected({ entry, preview: preview.slice(0, 50_000) });
    } catch (reason) {
      setError(errorMessage(reason));
    }
  };

  return (
    <div className="flex min-h-full flex-col">
      <div className="flex items-center gap-2 border-b border-current/10 p-3">
        <button
          type="button"
          disabled={!listing?.parent}
          onClick={() => { setSelected(null); void load(listing?.parent || undefined); }}
          className="flex h-8 w-8 items-center justify-center rounded border border-current/15 disabled:opacity-30"
          aria-label="Parent folder"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <span className="min-w-0 flex-1 truncate font-mono text-[0.68rem] text-text-secondary" title={listing?.path}>{listing?.path || "Workspace"}</span>
        <button type="button" onClick={() => void load(path)} className="flex h-8 w-8 items-center justify-center rounded border border-current/15" aria-label="Refresh files">
          <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
        </button>
      </div>
      {error && <div className="m-3 rounded border border-red-500/30 p-2 text-xs text-red-400">{error}</div>}
      {selected ? (
        <div className="min-h-0 flex-1 p-3">
          <button type="button" onClick={() => setSelected(null)} className="mb-3 flex items-center gap-1 text-xs text-text-secondary hover:text-midground">
            <ChevronLeft className="h-3.5 w-3.5" /> Back to files
          </button>
          <h3 className="truncate text-sm font-bold text-midground">{selected.entry.name}</h3>
          <p className="mt-1 font-mono text-[0.65rem] text-text-tertiary">{selected.entry.path}</p>
          {selected.preview !== undefined ? (
            <pre className="mt-4 max-h-[calc(100vh-16rem)] overflow-auto whitespace-pre-wrap break-words rounded border border-current/10 bg-black/20 p-3 font-mono text-[0.68rem] leading-relaxed text-text-secondary">{selected.preview}</pre>
          ) : (
            <div className="mt-6 rounded border border-current/10 p-4 text-xs text-text-tertiary">Preview is unavailable for this file type or size. Open Artifacts for download and file management.</div>
          )}
        </div>
      ) : (
        <div className="divide-y divide-current/5">
          {listing?.entries.map((entry) => (
            <button key={entry.path} type="button" onClick={() => void open(entry)} className="flex w-full items-center gap-2.5 px-4 py-2.5 text-left hover:bg-current/5">
              {entry.is_directory ? <Folder className="h-4 w-4 shrink-0 text-amber-400" /> : <File className="h-4 w-4 shrink-0 text-text-tertiary" />}
              <span className="min-w-0 flex-1 truncate text-xs text-text-secondary">{entry.name}</span>
              {entry.size != null && !entry.is_directory && <span className="text-[0.62rem] text-text-tertiary">{Math.max(1, Math.round(entry.size / 1024))} KB</span>}
            </button>
          ))}
          {!loading && listing?.entries.length === 0 && (
            <div className="flex flex-col items-center p-10 text-center text-xs text-text-tertiary"><FolderOpen className="mb-3 h-7 w-7" />This folder is empty.</div>
          )}
        </div>
      )}
    </div>
  );
}

function AgentDetails({
  info,
  profile,
  storedSessionId,
  onOpenChat,
  chatBusy,
  onModelChanged,
}: {
  info: Record<string, unknown>;
  profile: string;
  storedSessionId: string | null;
  onOpenChat: (sessionId: string) => Promise<void>;
  chatBusy: boolean;
  onModelChanged: () => void;
}) {
  const [modelOpen, setModelOpen] = useState(false);
  const [modelInfo, setModelInfo] = useState<{ model: string; provider: string } | null>(null);
  const [modelHealth, setModelHealth] = useState<{
    status: "checking" | "connected" | "missing" | "unknown";
    message: string;
  }>({ status: "checking", message: "Checking provider credentials" });
  const [liveServers, setLiveServers] = useState<Record<string, {
    status: "checking" | "connected" | "failed";
    tools?: number;
    error?: string;
  }>>({});
  const [recentChats, setRecentChats] = useState<SessionInfo[]>([]);
  const [recentChatsLoading, setRecentChatsLoading] = useState(true);
  const [recentChatsError, setRecentChatsError] = useState<string | null>(null);
  const [openingChat, setOpeningChat] = useState<string | null>(null);

  const refreshRecentChats = useCallback(async () => {
    setRecentChatsLoading(true);
    setRecentChatsError(null);
    try {
      const result = await api.getSessions(12, 0, profile, "recent");
      setRecentChats(result.sessions.filter((session) => session.message_count > 0).slice(0, 8));
    } catch (reason) {
      setRecentChatsError(errorMessage(reason));
    } finally {
      setRecentChatsLoading(false);
    }
  }, [profile]);

  const refreshModel = useCallback(async () => {
    setModelHealth({ status: "checking", message: "Checking provider credentials" });
    try {
      const [current, options] = await Promise.all([
        api.getModelInfo(profile),
        api.getModelOptions(profile),
      ]);
      setModelInfo({ model: current.model, provider: current.provider });
      const provider = options.providers.find((candidate) =>
        candidate.slug === current.provider ||
        candidate.name === current.provider ||
        candidate.aliases?.includes(current.provider),
      );
      if (provider?.authenticated === true) {
        setModelHealth({ status: "connected", message: "Provider credentials available" });
      } else if (provider?.authenticated === false) {
        setModelHealth({ status: "missing", message: provider.warning || "Provider credentials are missing" });
      } else {
        setModelHealth({ status: "unknown", message: "Configured; provider did not report credential health" });
      }
    } catch (reason) {
      setModelHealth({ status: "missing", message: errorMessage(reason) });
    }
  }, [profile]);

  useEffect(() => { void refreshModel(); }, [refreshModel]);
  useEffect(() => { void refreshRecentChats(); }, [refreshRecentChats, storedSessionId]);

  useEffect(() => {
    let cancelled = false;
    const checkConnections = async () => {
      try {
        const configured = (await api.getMcpServers()).servers.filter((server) => server.enabled);
        if (cancelled) return;
        setLiveServers(Object.fromEntries(configured.map((server) => [server.name, { status: "checking" as const }])));
        const checks = await Promise.all(configured.map(async (server) => {
          try {
            const result = await api.testMcpServer(server.name);
            return [server.name, result.ok
              ? { status: "connected" as const, tools: result.tools.length }
              : { status: "failed" as const, error: result.error || "Connection failed" }] as const;
          } catch (reason) {
            return [server.name, { status: "failed" as const, error: errorMessage(reason) }] as const;
          }
        }));
        if (!cancelled) setLiveServers(Object.fromEntries(checks));
      } catch {
        // The session inventory below remains a useful fallback when the
        // management endpoint is unavailable.
      }
    };
    void checkConnections();
    return () => { cancelled = true; };
  }, [profile]);

  const rows = [
    ["Agent", profile || textOf(info.profile_name) || "default"],
    ["Model", modelInfo?.model || textOf(info.model) || "Profile default"],
    ["Provider", modelInfo?.provider || textOf(info.provider) || "Configured provider"],
    ["Workspace", textOf(info.cwd) || "/opt/data/hermes"],
    ["Branch", textOf(info.branch) || "—"],
    ["Approval mode", textOf(info.approval_mode) || "Standard"],
  ];
  const inventoryServers = Array.isArray(info.mcp_servers) ? info.mcp_servers as Array<Record<string, unknown>> : [];
  const servers = Object.keys(liveServers).length
    ? Object.entries(liveServers).map(([name, result]) => ({ name, ...result }))
    : inventoryServers;
  return (
    <div className="space-y-5 p-4">
      <div>
        <h3 className="text-sm font-bold text-midground">Agent runtime</h3>
        <p className="mt-1 text-xs leading-relaxed text-text-tertiary">Live details for this conversation. Credentials and configuration remain in the existing protected settings pages.</p>
      </div>
      <dl className="divide-y divide-current/10 rounded-lg border border-current/10">
        {rows.map(([label, value]) => (
          <div key={label} className="grid grid-cols-[7rem_1fr] gap-3 px-3 py-2.5 text-xs">
            <dt className="text-text-tertiary">{label}</dt>
            <dd className="flex min-w-0 items-center justify-between gap-2 break-all font-mono text-text-secondary">
              <span>{value}</span>
              {label === "Model" && (
                <button
                  type="button"
                  onClick={() => setModelOpen(true)}
                  className="inline-flex shrink-0 items-center gap-1 rounded border border-current/15 px-2 py-1 font-sans text-[0.62rem] font-semibold uppercase tracking-[0.08em] hover:border-midground hover:text-midground"
                >
                  <Pencil className="h-3 w-3" /> Change
                </button>
              )}
            </dd>
          </div>
        ))}
        <div className="grid grid-cols-[7rem_1fr] gap-3 px-3 py-2.5 text-xs">
          <dt className="text-text-tertiary">Model status</dt>
          <dd className="min-w-0">
            <span className={cn(
              "inline-flex items-center gap-1.5 font-sans text-[0.65rem] font-semibold uppercase",
              modelHealth.status === "connected" ? "text-emerald-400" :
                modelHealth.status === "checking" ? "text-amber-400" :
                  modelHealth.status === "missing" ? "text-red-400" : "text-text-tertiary",
            )}>
              <span className={cn(
                "h-1.5 w-1.5 rounded-full",
                modelHealth.status === "connected" ? "bg-emerald-400" :
                  modelHealth.status === "checking" ? "animate-pulse bg-amber-400" :
                    modelHealth.status === "missing" ? "bg-red-400" : "bg-text-tertiary",
              )} />
              {modelHealth.status === "connected" ? "Connected" : modelHealth.status === "checking" ? "Checking" : modelHealth.status === "missing" ? "Needs attention" : "Unverified"}
            </span>
            <p className="mt-1 break-words font-sans text-[0.65rem] leading-relaxed text-text-tertiary">{modelHealth.message}</p>
          </dd>
        </div>
      </dl>
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-text-tertiary">Connections</h3>
        <div className="mt-2 space-y-2">
          {servers.length ? servers.map((server, index) => {
            const status = textOf(server.status) || "configured";
            const connected = /connected|ready/i.test(status);
            const checking = /checking|connecting/i.test(status);
            const toolCount = typeof server.tools === "number" ? server.tools : null;
            return (
            <div key={`${server.name}-${index}`} className="rounded border border-current/10 px-3 py-2 text-xs" title={textOf(server.error)}>
              <div className="flex items-center justify-between gap-3">
                <span className="truncate text-text-secondary">{textOf(server.name)}</span>
                <span className={cn(
                  "shrink-0 text-[0.65rem] font-semibold uppercase",
                  connected ? "text-emerald-400" : checking ? "text-amber-400" : "text-red-400",
                )}>{status}{connected && toolCount !== null ? ` · ${toolCount} tools` : ""}</span>
              </div>
              {server.error ? <p className="mt-1 line-clamp-2 text-[0.65rem] leading-relaxed text-red-400/80">{textOf(server.error)}</p> : null}
            </div>
          );
          }) : <p className="rounded border border-current/10 p-3 text-xs text-text-tertiary">Connection status will appear after the agent runtime reports it.</p>}
        </div>
      </div>
      <div>
        <div className="flex items-center justify-between gap-3">
          <h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-text-tertiary">
            <History className="h-3.5 w-3.5" /> Recent chats
          </h3>
          <button
            type="button"
            onClick={() => void refreshRecentChats()}
            disabled={recentChatsLoading}
            className="rounded p-1 text-text-tertiary hover:bg-current/5 hover:text-midground disabled:opacity-50"
            aria-label="Refresh recent chats"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", recentChatsLoading && "animate-spin")} />
          </button>
        </div>
        <div className="mt-2 space-y-1.5">
          {recentChatsError ? (
            <div className="rounded border border-red-500/30 p-2 text-[0.68rem] text-red-400">{recentChatsError}</div>
          ) : recentChatsLoading && recentChats.length === 0 ? (
            <div className="flex items-center gap-2 rounded border border-current/10 p-3 text-xs text-text-tertiary">
              <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> Loading chats…
            </div>
          ) : recentChats.length ? recentChats.map((session) => {
            const current = session.id === storedSessionId;
            const title = session.title?.trim() && session.title !== "Untitled"
              ? session.title
              : session.preview?.trim() || "Untitled chat";
            return (
              <button
                key={session.id}
                type="button"
                disabled={chatBusy || current || openingChat !== null}
                onClick={async () => {
                  setOpeningChat(session.id);
                  try {
                    await onOpenChat(session.id);
                  } finally {
                    setOpeningChat(null);
                  }
                }}
                className={cn(
                  "w-full rounded border px-3 py-2 text-left transition",
                  current
                    ? "border-emerald-400/35 bg-emerald-400/5"
                    : "border-current/10 hover:border-midground/40 hover:bg-current/5",
                  (chatBusy || openingChat !== null) && !current && "opacity-60",
                )}
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="min-w-0 truncate text-xs font-medium text-text-secondary">{title}</span>
                  {openingChat === session.id ? (
                    <LoaderCircle className="h-3.5 w-3.5 shrink-0 animate-spin text-amber-400" />
                  ) : current ? (
                    <span className="shrink-0 text-[0.6rem] font-semibold uppercase text-emerald-400">Current</span>
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5 shrink-0 text-text-tertiary" />
                  )}
                </span>
                <span className="mt-1 flex items-center gap-1.5 text-[0.64rem] text-text-tertiary">
                  <span>{timeAgo(session.last_active)}</span>
                  <span aria-hidden>·</span>
                  <span>{session.message_count} messages</span>
                </span>
              </button>
            );
          }) : (
            <p className="rounded border border-current/10 p-3 text-xs text-text-tertiary">No previous chats yet.</p>
          )}
        </div>
      </div>
      {modelOpen && (
        <ModelPickerDialog
          loader={() => api.getModelOptions(profile)}
          alwaysGlobal
          currentAssignment={modelInfo}
          onApply={async ({ provider, model, confirmExpensiveModel }) => {
            const result = await api.setModelAssignment({
              confirm_expensive_model: confirmExpensiveModel,
              scope: "main",
              provider,
              model,
            }, profile);
            if (!result.confirm_required) {
              await refreshModel();
              onModelChanged();
            }
            return result;
          }}
          onClose={() => {
            setModelOpen(false);
            void refreshModel();
          }}
        />
      )}
    </div>
  );
}
