"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { streamAssistant } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Sparkles, Send, User, AlertTriangle, Check, Loader2, Plus } from "lucide-react";

// One tool call the agent made, as shown in the live trace.
interface ToolStep {
  step: number;
  name: string;
  args: Record<string, unknown>;
  status: "running" | "done" | "error";
  summary?: string;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  steps?: ToolStep[];
  error?: boolean;
  streaming?: boolean;
}

// Where the conversation is cached in the browser so it survives leaving the
// tab and coming back (the backend also persists it per-thread; this restores
// the exact on-screen view incl. the tool traces without a round-trip).
const STORAGE_KEY = "vermio_assistant_chat_v1";

// Landlord-facing prompts: each mixes portfolio data with the law, which is the
// whole reason the agent exists (PRD J1–J7).
const SUGGESTIONS = [
  "Welche Mieter sind überfällig und um wie viel?",
  "Wie hoch ist die Kaution meiner ersten Wohnung — und was erlaubt das Gesetz?",
  "Wie viele Wohnungen habe ich und in welchen Häusern?",
  "Welche Kosten sind nach BetrKV umlagefähig?",
];

// Friendly German labels for the tools the agent calls. Unknown names fall back
// to the raw tool name so a new backend tool still shows up.
const TOOL_LABELS: Record<string, string> = {
  get_overdue_rent: "Mietrückstände prüfen",
  list_apartments: "Wohnungen auflisten",
  get_contract: "Mietvertrag abrufen",
  get_payments: "Zahlungen abrufen",
  get_tax_report: "Steuerübersicht berechnen",
  search_legal_corpus: "Gesetzestext durchsuchen",
};

// Render a tool's arguments compactly, like "apartment_id: 1" — the "command".
function argsInline(args: Record<string, unknown>): string {
  const entries = Object.entries(args);
  if (entries.length === 0) return "";
  return entries.map(([k, v]) => `${k}: ${String(v)}`).join(", ");
}

function ToolTrace({ steps }: { steps: ToolStep[] }) {
  return (
    <div className="rounded-lg border border-border bg-muted/40 divide-y divide-border overflow-hidden">
      {steps.map((s) => (
        <div key={s.step} className="flex items-start gap-2 px-2.5 py-1.5">
          <span className="mt-0.5 shrink-0">
            {s.status === "running" ? (
              <Loader2 className="size-3.5 text-muted-foreground animate-spin" />
            ) : s.status === "error" ? (
              <AlertTriangle className="size-3.5 text-destructive" />
            ) : (
              <Check className="size-3.5 text-emerald-600 dark:text-emerald-500" />
            )}
          </span>
          <div className="min-w-0 flex-1">
            <div className="font-mono text-[11px] leading-tight truncate">
              <span className="text-foreground">{TOOL_LABELS[s.name] || s.name}</span>
              {argsInline(s.args) && (
                <span className="text-muted-foreground"> ({argsInline(s.args)})</span>
              )}
            </div>
            {s.summary && (
              <div
                className={`text-[11px] leading-tight truncate ${
                  s.status === "error" ? "text-destructive" : "text-muted-foreground"
                }`}
              >
                {s.summary}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function AskPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  // Becomes true once we've read any saved conversation from localStorage, so
  // the persist effect below doesn't overwrite the cache with the empty initial
  // state before restore has run.
  const [hydrated, setHydrated] = useState(false);
  // The conversation id, assigned by the backend on the first answer and sent
  // back on every subsequent turn so the agent keeps context (R4). A ref, not
  // state, so it can't go stale inside the send callback.
  const threadIdRef = useRef<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  // Restore the previous conversation on mount (runs after hydration, so it
  // can't cause an SSR/client mismatch). Any half-streamed turn from before a
  // navigation is settled by clearing its `streaming` flag.
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as { threadId: number | null; messages: ChatMessage[] };
        if (Array.isArray(saved.messages) && saved.messages.length > 0) {
          setMessages(saved.messages.map((m) => ({ ...m, streaming: false })));
          threadIdRef.current = saved.threadId ?? null;
        }
      }
    } catch {
      /* corrupt cache — ignore and start fresh */
    }
    setHydrated(true);
  }, []);

  // Persist the conversation whenever it settles (not on every streamed token,
  // hence the `pending` gate). Cleared to empty by "Neues Gespräch".
  useEffect(() => {
    if (!hydrated || pending) return;
    try {
      if (messages.length > 0) {
        localStorage.setItem(
          STORAGE_KEY,
          JSON.stringify({ threadId: threadIdRef.current, messages }),
        );
      } else {
        localStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      /* quota exceeded / storage disabled — non-fatal */
    }
  }, [messages, pending, hydrated]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, pending]);

  const send = useCallback(async (question: string) => {
    const q = question.trim();
    if (!q || pending) return;
    setInput("");
    setPending(true);
    // Push the user turn plus an empty assistant turn we fill in as the stream
    // arrives. Everything below patches this last (assistant) message.
    setMessages((m) => [
      ...m,
      { role: "user", content: q },
      { role: "assistant", content: "", steps: [], streaming: true },
    ]);
    const patchLast = (fn: (a: ChatMessage) => ChatMessage) =>
      setMessages((m) => {
        const copy = m.slice();
        copy[copy.length - 1] = fn(copy[copy.length - 1]);
        return copy;
      });

    try {
      await streamAssistant(
        { question: q, thread_id: threadIdRef.current },
        {
          onMeta: (tid) => {
            threadIdRef.current = tid;
          },
          // Add a trace row the moment the agent reaches for a tool, with the
          // arguments it chose — the user watches the steps happen live.
          onTool: (step, name, args) =>
            patchLast((a) => ({
              ...a,
              steps: [...(a.steps ?? []), { step, name, args, status: "running" }],
            })),
          // Flip that row to done/error and attach the short result summary.
          onToolResult: (step, ok, summary) =>
            patchLast((a) => ({
              ...a,
              steps: (a.steps ?? []).map((s) =>
                s.step === step ? { ...s, status: ok ? "done" : "error", summary } : s
              ),
            })),
          onToken: (t) => patchLast((a) => ({ ...a, content: a.content + t })),
          onDone: () => patchLast((a) => ({ ...a, streaming: false })),
          onError: (detail) =>
            patchLast((a) => ({ ...a, content: detail, error: true, streaming: false })),
        },
      );
    } catch {
      patchLast((a) => ({
        ...a,
        content: "Verbindung zum Assistenten fehlgeschlagen. Bitte erneut versuchen.",
        error: true,
        streaming: false,
      }));
    } finally {
      setPending(false);
      taRef.current?.focus();
    }
  }, [pending]);

  const newConversation = useCallback(() => {
    if (pending) return;
    threadIdRef.current = null;
    setMessages([]);
    setInput("");
    taRef.current?.focus();
  }, [pending]);

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-2rem)] md:h-[calc(100vh-3rem)] max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-2.5 pb-3 border-b border-border">
        <div className="flex size-8 items-center justify-center rounded-lg bg-primary/15 text-primary">
          <Sparkles className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <h1 className="text-sm font-semibold leading-tight">Ask Vermio</h1>
          <p className="text-xs text-muted-foreground truncate">
            Fragen zu deinem Portfolio &amp; Mietrecht — Antworten aus deinen echten Daten und den Quellen (BGB, BetrKV)
          </p>
        </div>
        {messages.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            className="shrink-0 gap-1.5 text-muted-foreground"
            onClick={newConversation}
            disabled={pending}
          >
            <Plus className="size-4" />
            <span className="hidden sm:inline">Neues Gespräch</span>
          </Button>
        )}
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto py-4 space-y-4">
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center gap-4">
            <div className="flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
              <Sparkles className="size-6" />
            </div>
            <div>
              <p className="font-medium">Wie kann ich helfen?</p>
              <p className="text-sm text-muted-foreground mt-1">
                Der Assistent liest deine echten Portfolio-Daten und die hinterlegten Rechtsquellen — und zeigt dir Schritt für Schritt, was er dafür abfragt.
              </p>
            </div>
            <div className="grid sm:grid-cols-2 gap-2 w-full max-w-lg">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="text-left text-sm rounded-lg border border-border px-3 py-2 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="flex justify-end gap-2">
              <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-primary/15 text-foreground px-3.5 py-2 text-sm whitespace-pre-wrap">
                {m.content}
              </div>
              <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground mt-0.5">
                <User className="size-4" />
              </div>
            </div>
          ) : (
            <div key={i} className="flex gap-2">
              <div
                className={`flex size-7 shrink-0 items-center justify-center rounded-full mt-0.5 ${
                  m.error
                    ? "bg-destructive/15 text-destructive"
                    : "bg-primary/15 text-primary"
                }`}
              >
                {m.error ? <AlertTriangle className="size-4" /> : <Sparkles className="size-4" />}
              </div>
              <div className="max-w-[85%] space-y-2">
                {/* The live tool trace — each step with its args + result. */}
                {m.steps && m.steps.length > 0 && <ToolTrace steps={m.steps} />}

                {m.streaming && !m.content ? (
                  // Waiting for the first token (tool rounds are running).
                  <div className="rounded-2xl rounded-tl-sm bg-muted px-3.5 py-2.5 w-fit">
                    <span className="flex gap-1">
                      <span className="size-1.5 rounded-full bg-muted-foreground/60 animate-bounce [animation-delay:-0.3s]" />
                      <span className="size-1.5 rounded-full bg-muted-foreground/60 animate-bounce [animation-delay:-0.15s]" />
                      <span className="size-1.5 rounded-full bg-muted-foreground/60 animate-bounce" />
                    </span>
                  </div>
                ) : (
                  m.content && (
                    <div
                      className={`rounded-2xl rounded-tl-sm px-3.5 py-2 text-sm whitespace-pre-wrap ${
                        m.error
                          ? "bg-destructive/10 text-destructive"
                          : "bg-muted text-foreground"
                      }`}
                    >
                      {m.content}
                      {m.streaming && (
                        <span className="inline-block w-1.5 h-4 -mb-0.5 ml-0.5 bg-foreground/60 animate-pulse" />
                      )}
                    </div>
                  )
                )}
              </div>
            </div>
          )
        )}
      </div>

      {/* Composer */}
      <div className="border-t border-border pt-3">
        <div className="flex items-end gap-2">
          <Textarea
            ref={taRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Frage zu deinem Portfolio oder Mietrecht…"
            rows={1}
            className="min-h-10 max-h-40 resize-none"
            disabled={pending}
          />
          <Button
            size="icon"
            className="size-10 shrink-0"
            onClick={() => send(input)}
            disabled={pending || !input.trim()}
            aria-label="Send"
          >
            <Send className="size-4" />
          </Button>
        </div>
        <p className="text-[10px] text-muted-foreground mt-1.5 text-center">
          Keine Rechtsberatung. Im Zweifel anwaltlich prüfen lassen. Enter zum Senden, Shift+Enter für neue Zeile.
        </p>
      </div>
    </div>
  );
}
