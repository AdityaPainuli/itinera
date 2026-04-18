"use client";

import { useEffect, useState } from "react";
import type { AgentEvent } from "@/lib/api";

interface Props {
  events: AgentEvent[];
  startedAt: number; // Date.now() when the request began
}

// Ordered stages the UI wants to reflect. We mark each "done" the moment we
// see any event from a *later* stage — that's the cheap way to show a
// check-list without the backend emitting explicit start/end for each.
const STAGES = [
  { key: "researching", label: "Researching the destination" },
  { key: "synthesizing", label: "Writing the day-by-day plan" },
  { key: "validating", label: "Verifying budget & route" },
  { key: "repairing", label: "Fixing flagged issues" },
  { key: "done", label: "Saving" },
] as const;

type StageKey = (typeof STAGES)[number]["key"];

const STAGE_ORDER: Record<StageKey, number> = {
  researching: 0,
  synthesizing: 1,
  validating: 2,
  repairing: 3,
  done: 4,
};

export function ProgressPanel({ events, startedAt }: Props) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(id);
  }, []);

  const elapsed = Math.max(0, Math.floor((now - startedAt) / 1000));
  const searches = events.filter((e): e is Extract<AgentEvent, { kind: "search" }> => e.kind === "search");
  const validating = events.find((e): e is Extract<AgentEvent, { kind: "validating" }> => e.kind === "validating");
  const repairing = events.find((e): e is Extract<AgentEvent, { kind: "repairing" }> => e.kind === "repairing");
  const isDone = events.some((e) => e.kind === "done");

  // The highest stage we've seen. Any later stage implies earlier stages completed.
  const currentStage: StageKey = events.reduce<StageKey>((acc, ev) => {
    if (ev.kind in STAGE_ORDER) {
      const k = ev.kind as StageKey;
      return STAGE_ORDER[k] > STAGE_ORDER[acc] ? k : acc;
    }
    return acc;
  }, "researching");

  const stageStatus = (key: StageKey): "done" | "active" | "pending" | "skipped" => {
    const currentIdx = STAGE_ORDER[currentStage];
    const idx = STAGE_ORDER[key];
    if (isDone && key === "done") return "done";
    if (idx < currentIdx) return "done";
    if (idx === currentIdx) return "active";
    // Repair only runs when validating found issues.
    if (key === "repairing" && validating && validating.issues === 0) return "skipped";
    return "pending";
  };

  return (
    <div className="bg-white border border-ink-200 rounded-xl p-5">
      <div className="flex items-baseline justify-between mb-4">
        <h2 className="font-serif text-xl text-ink-900">Planning your trip</h2>
        <span className="text-sm text-ink-500 tabular-nums">{formatElapsed(elapsed)}</span>
      </div>

      <ul className="space-y-2">
        {STAGES.map((s) => {
          const status = stageStatus(s.key);
          return (
            <li key={s.key} className="flex items-center gap-3 text-sm">
              <StageIcon status={status} />
              <span
                className={
                  status === "done"
                    ? "text-ink-700"
                    : status === "active"
                      ? "text-ink-900 font-medium"
                      : status === "skipped"
                        ? "text-ink-400 line-through"
                        : "text-ink-400"
                }
              >
                {s.label}
                {s.key === "validating" && validating && (
                  <span className="ml-2 text-xs text-ink-500">
                    ({validating.issues} issue{validating.issues === 1 ? "" : "s"} found)
                  </span>
                )}
                {s.key === "repairing" && repairing && (
                  <span className="ml-2 text-xs text-ink-500">
                    ({repairing.issues} to fix)
                  </span>
                )}
              </span>
            </li>
          );
        })}
      </ul>

      {searches.length > 0 && (
        <div className="mt-5 pt-4 border-t border-ink-100">
          <div className="text-xs uppercase tracking-wide text-ink-500 mb-2">
            Web searches ({searches.length})
          </div>
          <ul className="space-y-1.5 text-sm text-ink-700">
            {searches.map((s, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="text-saffron-600 mt-0.5">🔎</span>
                <span className="truncate">{s.query}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-5 pt-4 border-t border-ink-100 text-xs text-ink-500">
        Typical generation takes 30–90 seconds. Claude is doing live web research —
        opening hours, current prices, and real restaurants — so this takes longer
        than a generic itinerary but produces concrete, verifiable results.
      </div>
    </div>
  );
}

function StageIcon({ status }: { status: "done" | "active" | "pending" | "skipped" }) {
  if (status === "done")
    return (
      <span className="w-5 h-5 rounded-full bg-green-100 text-green-700 flex items-center justify-center text-xs">
        ✓
      </span>
    );
  if (status === "active")
    return (
      <span className="w-5 h-5 rounded-full border-2 border-saffron-500 border-t-transparent animate-spin" />
    );
  if (status === "skipped")
    return (
      <span className="w-5 h-5 rounded-full bg-ink-100 text-ink-400 flex items-center justify-center text-xs">
        —
      </span>
    );
  return <span className="w-5 h-5 rounded-full border-2 border-ink-200" />;
}

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}:${s.toString().padStart(2, "0")}` : `${s}s`;
}
