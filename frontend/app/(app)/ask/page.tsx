"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { RagAnswer, RagCitation } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Sparkles, Send, User, AlertTriangle, BookOpen } from "lucide-react";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: RagCitation[];
  latency_ms?: number;
  refused?: boolean;
  error?: boolean;
}

const SUGGESTIONS = [
  "Welche Kosten sind nach BetrKV umlagefähig?",
  "Wie hoch darf die Mietkaution sein?",
  "Innerhalb welcher Frist muss die Nebenkostenabrechnung erfolgen?",
  "Muss ich die Kaution verzinsen?",
];

export default function AskPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, pending]);

  const send = useCallback(async (question: string) => {
    const q = question.trim();
    if (!q || pending) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: q }]);
    setPending(true);
    try {
      const { data } = await api.post<RagAnswer>("/api/rag/ask", { question: q });
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: data.answer,
          citations: data.citations,
          latency_ms: data.latency_ms,
          refused: data.refused,
        },
      ]);
    } catch (e: any) {
      const d = e?.response?.data?.detail;
      const detail =
        typeof d === "string"
          ? d
          : e?.response?.status >= 500
          ? "The assistant is unavailable. Check that GROQ_API_KEY is set and the RAG index is built (python -m rag.build_index)."
          : "Request failed. Please try again.";
      setMessages((m) => [...m, { role: "assistant", content: detail, error: true }]);
    } finally {
      setPending(false);
      taRef.current?.focus();
    }
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
        <div>
          <h1 className="text-sm font-semibold leading-tight">Ask Vermio</h1>
          <p className="text-xs text-muted-foreground">
            Fragen zu Mietrecht &amp; Nebenkosten — Antworten mit Quellen (BGB, BetrKV, Vermio-Doku)
          </p>
        </div>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto py-4 space-y-4">
        {messages.length === 0 && !pending && (
          <div className="h-full flex flex-col items-center justify-center text-center gap-4">
            <div className="flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
              <Sparkles className="size-6" />
            </div>
            <div>
              <p className="font-medium">Wie kann ich helfen?</p>
              <p className="text-sm text-muted-foreground mt-1">
                Der Assistent beantwortet nur, was in den hinterlegten Quellen belegt ist.
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
                <div
                  className={`rounded-2xl rounded-tl-sm px-3.5 py-2 text-sm whitespace-pre-wrap ${
                    m.error
                      ? "bg-destructive/10 text-destructive"
                      : m.refused
                      ? "bg-amber-500/10 text-foreground"
                      : "bg-muted text-foreground"
                  }`}
                >
                  {m.content}
                </div>

                {m.citations && m.citations.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5">
                    <BookOpen className="size-3.5 text-muted-foreground" />
                    {m.citations.map((c, j) => (
                      <Badge key={j} variant="secondary" className="font-normal gap-1">
                        <span>{[c.law_ref, c.section].filter(Boolean).join(" · ") || "Quelle"}</span>
                        <span className="text-muted-foreground tabular-nums">{c.score.toFixed(2)}</span>
                      </Badge>
                    ))}
                  </div>
                )}

                {typeof m.latency_ms === "number" && (
                  <p className="text-[10px] text-muted-foreground">
                    {(m.latency_ms / 1000).toFixed(1)}s
                    {m.refused && " · keine ausreichende Quelle gefunden"}
                  </p>
                )}
              </div>
            </div>
          )
        )}

        {pending && (
          <div className="flex gap-2">
            <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary mt-0.5">
              <Sparkles className="size-4" />
            </div>
            <div className="rounded-2xl rounded-tl-sm bg-muted px-3.5 py-2.5">
              <span className="flex gap-1">
                <span className="size-1.5 rounded-full bg-muted-foreground/60 animate-bounce [animation-delay:-0.3s]" />
                <span className="size-1.5 rounded-full bg-muted-foreground/60 animate-bounce [animation-delay:-0.15s]" />
                <span className="size-1.5 rounded-full bg-muted-foreground/60 animate-bounce" />
              </span>
            </div>
          </div>
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
            placeholder="Frage zu Mietrecht oder Nebenkosten…"
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
