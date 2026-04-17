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
