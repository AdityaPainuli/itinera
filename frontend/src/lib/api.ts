import type { Itinerary, ItineraryListItem, ItineraryRequest } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export async function generateItinerary(req: ItineraryRequest): Promise<Itinerary> {
  const res = await fetch(`${API_BASE}/api/itinerary/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  return handle<Itinerary>(res);
}

// Event shapes emitted by the agent stream. Kept in sync with
// backend/app/agents/itinerary_agent.py EventKind.
export type AgentEvent =
  | { kind: "researching" }
  | { kind: "search"; query: string; status: "running" | "done" }
  | { kind: "synthesizing" }
  | { kind: "weather" }
  | { kind: "validating"; issues: number }
  | { kind: "repairing"; issues: number }
  | { kind: "done"; itinerary: Itinerary }
  | { kind: "error"; message: string };

/** Stream itinerary generation over SSE. Resolves with the final itinerary. */
export async function generateItineraryStream(
  req: ItineraryRequest,
  onEvent: (ev: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<Itinerary> {
  const res = await fetch(`${API_BASE}/api/itinerary/generate/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(req),
    signal,
  });

  if (!res.ok || !res.body) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalItinerary: Itinerary | null = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE messages are separated by blank lines.
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const rawMessage = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);

      // Join all `data:` lines for this message (SSE allows multi-line data).
      const dataLines: string[] = [];
      for (const line of rawMessage.split("\n")) {
        if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
      }
      if (!dataLines.length) continue;

      let ev: AgentEvent;
      try {
        ev = JSON.parse(dataLines.join("\n")) as AgentEvent;
      } catch {
        continue;
      }
      onEvent(ev);

      if (ev.kind === "done") finalItinerary = ev.itinerary;
      else if (ev.kind === "error") throw new Error(ev.message);
    }
  }

  if (!finalItinerary) throw new Error("stream ended before itinerary was produced");
  return finalItinerary;
}

export async function listItineraries(): Promise<ItineraryListItem[]> {
  const res = await fetch(`${API_BASE}/api/itinerary`);
  return handle<ItineraryListItem[]>(res);
}

export async function getItinerary(id: string): Promise<Itinerary> {
  const res = await fetch(`${API_BASE}/api/itinerary/${id}`);
  return handle<Itinerary>(res);
}

export async function getItineraryMarkdown(id: string): Promise<string> {
  const res = await fetch(`${API_BASE}/api/itinerary/${id}/markdown`);
  if (!res.ok) throw new Error(`${res.status}: ${res.statusText}`);
  return res.text();
}

export async function deleteItinerary(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/itinerary/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`${res.status}: ${res.statusText}`);
}
