"use client";

import { useCallback, useEffect, useState } from "react";
import { HistoryList } from "@/components/HistoryList";
import { ItineraryDisplay } from "@/components/ItineraryDisplay";
import { ItineraryForm } from "@/components/ItineraryForm";
import {
  deleteItinerary,
  generateItinerary,
  getItinerary,
  getItineraryMarkdown,
  listItineraries,
} from "@/lib/api";
import type { Itinerary, ItineraryListItem, ItineraryRequest } from "@/lib/types";

export default function Home() {
  const [history, setHistory] = useState<ItineraryListItem[]>([]);
  const [current, setCurrent] = useState<Itinerary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshHistory = useCallback(async () => {
    try {
      setHistory(await listItineraries());
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    refreshHistory();
  }, [refreshHistory]);

  const handleGenerate = async (req: ItineraryRequest) => {
    setLoading(true);
    setError(null);
    setCurrent(null);
    try {
      const result = await generateItinerary(req);
      setCurrent(result);
      await refreshHistory();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to generate itinerary");
    } finally {
      setLoading(false);
    }
  };

  const handleSelect = async (id: string) => {
    setError(null);
    try {
      setCurrent(await getItinerary(id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load itinerary");
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteItinerary(id);
      if (current?.id === id) setCurrent(null);
      await refreshHistory();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete");
    }
  };

  const handleExportMarkdown = async () => {
    if (!current?.id) return;
    const md = await getItineraryMarkdown(current.id);
    downloadFile(`${current.request.destination}-${current.request.duration_days}d.md`, md, "text/markdown");
  };

  const handleExportJson = () => {
    if (!current) return;
    downloadFile(
      `${current.request.destination}-${current.request.duration_days}d.json`,
      JSON.stringify(current, null, 2),
      "application/json",
    );
  };

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      <div className="flex flex-col md:flex-row gap-8">
        <HistoryList
          items={history}
          activeId={current?.id}
          onSelect={handleSelect}
          onDelete={handleDelete}
          onNew={() => setCurrent(null)}
        />

        <div className="flex-1 min-w-0">
          {error && (
            <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
              {error}
            </div>
          )}

          {current ? (
            <ItineraryDisplay
              itinerary={current}
              onExportMarkdown={handleExportMarkdown}
              onExportJson={handleExportJson}
            />
          ) : (
            <div className="bg-white border border-ink-200 rounded-xl p-6">
              <h1 className="font-serif text-2xl text-ink-900 mb-1">Plan a trip</h1>
              <p className="text-ink-500 text-sm mb-6">
                Describe what you want. The agent researches current prices, attractions, and logistics on the
                web, then builds a concrete day-by-day plan.
              </p>
              <ItineraryForm onSubmit={handleGenerate} loading={loading} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function downloadFile(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
