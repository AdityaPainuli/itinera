"use client";

import type { ItineraryListItem } from "@/lib/types";

interface Props {
  items: ItineraryListItem[];
  activeId?: string;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onNew: () => void;
}

export function HistoryList({ items, activeId, onSelect, onDelete, onNew }: Props) {
  return (
    <aside className="w-full md:w-64 shrink-0">
      <button
        onClick={onNew}
        className="w-full py-2 mb-3 rounded-lg bg-ink-900 text-ink-50 text-sm font-medium hover:bg-ink-800"
      >
        + New itinerary
      </button>
      <div className="text-xs uppercase tracking-wide text-ink-500 mb-2 px-1">History</div>
      {items.length === 0 ? (
        <div className="text-sm text-ink-400 px-1">No itineraries yet.</div>
      ) : (
        <ul className="space-y-1">
          {items.map((it) => {
            const active = it.id === activeId;
            return (
              <li
                key={it.id}
                className={`group flex items-start gap-1 rounded-lg px-2 py-2 text-sm cursor-pointer transition ${
                  active ? "bg-ink-200" : "hover:bg-ink-100"
                }`}
                onClick={() => onSelect(it.id)}
              >
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-ink-800 truncate">{it.destination}</div>
                  <div className="text-xs text-ink-500">
                    {it.duration_days}d · {new Date(it.created_at).toLocaleDateString()}
                  </div>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm(`Delete ${it.destination}?`)) onDelete(it.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 text-ink-400 hover:text-red-600 text-xs px-1"
                  title="Delete"
                >
                  ✕
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
