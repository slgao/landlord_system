import axios from "axios";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Where the Ask Dachly conversation is cached in the browser (see /ask). Exposed
// here so every session-end path can wipe it — the cache holds the landlord's
// own portfolio answers and must not survive a logout or a switch of user.
export const ASSISTANT_CACHE_KEY = "dachly_assistant_chat_v1";

export function clearAssistantCache() {
  if (typeof window !== "undefined") localStorage.removeItem(ASSISTANT_CACHE_KEY);
}

export const api = axios.create({
  baseURL: BASE,
  // A backstop only: without it a hung request would hold a queue slot (below)
  // for ever. Generous, because PDF generation is genuinely slow.
  timeout: 60_000,
});

// ── One request at a time ────────────────────────────────────────────────────
// Counter-intuitive, and measured rather than assumed: firing a page's queries
// in parallel is *slower* than running them one after another, because the
// database is remote and serialises the work anyway — the concurrency only adds
// connection contention on top. Six calls take 2740 ms fired together and
// 542 ms queued; the dashboard's three take 1162 ms against 484 ms.
//
// Raise this if the database ever moves next to the API, where real parallelism
// would pay: then the queue is the thing costing you time.
const MAX_IN_FLIGHT = 1;

let active = 0;
const waiting: Array<() => void> = [];

function acquireSlot(): Promise<void> {
  if (active < MAX_IN_FLIGHT) {
    active += 1;
    return Promise.resolve();
  }
  return new Promise((resolve) => waiting.push(() => { active += 1; resolve(); }));
}

function releaseSlot() {
  active = Math.max(0, active - 1);
  waiting.shift()?.();
}

/** Downloads skip the queue: they are user-initiated, can take seconds, and
 *  must not sit in front of the data a page is waiting for. */
function isQueued(config: { responseType?: string }) {
  return config.responseType !== "blob" && config.responseType !== "arraybuffer";
}

/** The message to show for a failed request: the API's own `detail` when it
 *  sent one (a 409 "still has contracts", a 422 field error), otherwise the
 *  caller's fallback. Without this every failure read "Failed to save". */
export function errorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) && typeof detail[0]?.msg === "string") return detail[0].msg;
  return fallback;
}

api.interceptors.request.use(async (config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  if (isQueued(config)) {
    await acquireSlot();
    // Marked on the config so the response side releases exactly what it took,
    // even for a request that failed before reaching the server.
    (config as { _queued?: boolean })._queued = true;
  }
  return config;
});

api.interceptors.response.use(
  (r) => {
    if ((r.config as { _queued?: boolean })?._queued) releaseSlot();
    return r;
  },
  (err) => {
    // Release before anything else can throw, or one failure would wedge the
    // queue and every later request would hang waiting for a slot.
    if ((err.config as { _queued?: boolean })?._queued) releaseSlot();
    if (err.response?.status === 401 && typeof window !== "undefined") {
      localStorage.removeItem("token");
      clearAssistantCache();
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export async function login(email: string, password: string) {
  // The backend reads `username` as the email (kept for API compatibility).
  const res = await axios.post(`${BASE}/api/auth/token`, { username: email, password });
  const token: string = res.data.access_token;
  localStorage.setItem("token", token);
  return token;
}

export async function register(email: string, password: string, displayName?: string) {
  const res = await axios.post(`${BASE}/api/auth/register`, {
    email, password, display_name: displayName || null,
  });
  const token: string = res.data.access_token;
  localStorage.setItem("token", token);
  return token;
}

export function logout() {
  localStorage.removeItem("token");
  clearAssistantCache();
  window.location.href = "/login";
}

export function isAuthenticated() {
  if (typeof window === "undefined") return false;
  return !!localStorage.getItem("token");
}

// ── Assistant streaming (SSE over POST) ───────────────────────────────────────
// EventSource can't do POST or send an Authorization header, so we read the SSE
// stream by hand with fetch + a ReadableStream reader. Each server frame is
// `data: {json}\n\n`; we buffer, split on blank lines, and dispatch by type.

export interface AssistantStreamHandlers {
  onMeta?: (threadId: number) => void;   // conversation id, arrives first
  // A tool the agent is about to run, with the arguments it chose ("the command").
  onTool?: (step: number, name: string, args: Record<string, unknown>) => void;
  // That tool finished: ok/fail + a short result summary.
  onToolResult?: (step: number, ok: boolean, summary: string) => void;
  onToken?: (text: string) => void;       // a slice of the streamed answer
  onDone?: (toolsConsulted: string[]) => void;
  onError?: (detail: string) => void;
}

export async function streamAssistant(
  body: { question: string; thread_id: number | null },
  handlers: AssistantStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  const res = await fetch(`${BASE}/api/assistant/ask/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
  });

  if (res.status === 401) {
    // Mirror the axios interceptor: drop the token + cached chat, bounce to login.
    if (typeof window !== "undefined") {
      localStorage.removeItem("token");
      clearAssistantCache();
      window.location.href = "/login";
    }
    return;
  }
  if (!res.ok || !res.body) {
    let detail = `Request failed (${res.status}).`;
    try {
      const j = await res.json();
      if (typeof j?.detail === "string") detail = j.detail;
    } catch {
      /* non-JSON body — keep the generic message */
    }
    handlers.onError?.(detail);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // A complete frame ends with a blank line; keep the trailing partial.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      const dataLine = frame.split("\n").find((l) => l.startsWith("data:"));
      if (!dataLine) continue;
      const payload = dataLine.slice(5).trim();
      if (!payload) continue;
      let ev: any;
      try {
        ev = JSON.parse(payload);
      } catch {
        continue; // ignore a malformed frame rather than break the stream
      }
      switch (ev.type) {
        case "meta":
          handlers.onMeta?.(ev.thread_id);
          break;
        case "tool":
          handlers.onTool?.(ev.step, ev.name, ev.args ?? {});
          break;
        case "tool_result":
          handlers.onToolResult?.(ev.step, ev.ok, ev.summary ?? "");
          break;
        case "token":
          handlers.onToken?.(ev.content);
          break;
        case "done":
          handlers.onDone?.(ev.tools_consulted ?? []);
          break;
        case "error":
          handlers.onError?.(ev.detail ?? "Unbekannter Fehler.");
          break;
      }
    }
  }
}
