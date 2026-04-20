"use client";

import { useState } from "react";
import type { ItineraryRequest, TravelStyle } from "@/lib/types";

const STYLES: TravelStyle[] = [
  "cultural",
  "adventure",
  "food",
  "relaxation",
  "nature",
  "spiritual",
  "shopping",
  "nightlife",
  "photography",
  "family",
];

const PRESETS: { label: string; value: Partial<ItineraryRequest> }[] = [
  {
    label: "Udaipur weekend",
    value: {
      destination: "Udaipur, Rajasthan",
      duration_days: 3,
      budget_inr: 25000,
      travelers: 2,
      travel_styles: ["cultural", "photography"],
    },
  },
  {
    label: "Kerala 7-day",
    value: {
      destination: "Kerala (Kochi → Munnar → Alleppey)",
      duration_days: 7,
      budget_inr: 60000,
      travelers: 2,
      travel_styles: ["nature", "relaxation", "food"],
    },
  },
  {
    label: "Jaipur long weekend",
    value: {
      destination: "Jaipur, Rajasthan",
      duration_days: 4,
      budget_inr: 35000,
      travelers: 2,
      travel_styles: ["cultural", "food", "shopping"],
    },
  },
];

interface Props {
  onSubmit: (req: ItineraryRequest) => void;
  loading: boolean;
}

export function ItineraryForm({ onSubmit, loading }: Props) {
  const [destination, setDestination] = useState("");
  const [durationDays, setDurationDays] = useState(3);
  const [budget, setBudget] = useState(25000);
  const [travelers, setTravelers] = useState(2);
  const [styles, setStyles] = useState<TravelStyle[]>([]);
  const [specialInstructions, setSpecialInstructions] = useState("");
  const [startDate, setStartDate] = useState("");

  const toggleStyle = (s: TravelStyle) => {
    setStyles((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));
  };

  const applyPreset = (p: Partial<ItineraryRequest>) => {
    if (p.destination) setDestination(p.destination);
    if (p.duration_days) setDurationDays(p.duration_days);
    if (p.budget_inr) setBudget(p.budget_inr);
    if (p.travelers) setTravelers(p.travelers);
    if (p.travel_styles) setStyles(p.travel_styles);
  };

  const handleSubmit = () => {
    if (!destination.trim()) return;
    onSubmit({
      destination: destination.trim(),
      duration_days: durationDays,
      budget_inr: budget,
      travelers,
      travel_styles: styles,
      special_instructions: specialInstructions.trim() || undefined,
      start_date: startDate || undefined,
    });
  };

  return (
    <div className="space-y-5">
      <div>
        <div className="text-xs uppercase tracking-wide text-ink-500 mb-2">Quick start</div>
        <div className="flex flex-wrap gap-2">
          {PRESETS.map((p) => (
            <button
              key={p.label}
              onClick={() => applyPreset(p.value)}
              className="px-3 py-1.5 text-sm rounded-full border border-ink-200 bg-white hover:border-saffron-500 transition"
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-ink-700 mb-1">Destination</label>
        <input
          type="text"
          value={destination}
          onChange={(e) => setDestination(e.target.value)}
          placeholder="e.g. Udaipur, or Kerala (Kochi → Munnar → Alleppey)"
          className="w-full px-3 py-2 border border-ink-200 rounded-lg bg-white focus:outline-none focus:border-saffron-500"
        />
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div>
          <label className="block text-sm font-medium text-ink-700 mb-1">Days</label>
          <input
            type="number"
            min={1}
            max={30}
            value={durationDays}
            onChange={(e) => setDurationDays(Number(e.target.value))}
            className="w-full px-3 py-2 border border-ink-200 rounded-lg bg-white focus:outline-none focus:border-saffron-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-ink-700 mb-1">Travelers</label>
          <input
            type="number"
            min={1}
            max={100}
            value={travelers}
            onChange={(e) => setTravelers(Number(e.target.value))}
            className="w-full px-3 py-2 border border-ink-200 rounded-lg bg-white focus:outline-none focus:border-saffron-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-ink-700 mb-1">Budget (₹)</label>
          <input
            type="number"
            min={0}
            step={1000}
            value={budget}
            onChange={(e) => setBudget(Number(e.target.value))}
            className="w-full px-3 py-2 border border-ink-200 rounded-lg bg-white focus:outline-none focus:border-saffron-500"
          />
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-ink-700 mb-1">Start date (optional)</label>
        <input
          type="date"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
          className="px-3 py-2 border border-ink-200 rounded-lg bg-white focus:outline-none focus:border-saffron-500"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-ink-700 mb-2">Travel styles</label>
        <div className="flex flex-wrap gap-2">
          {STYLES.map((s) => {
            const active = styles.includes(s);
            return (
              <button
                key={s}
                onClick={() => toggleStyle(s)}
                className={`px-3 py-1.5 text-sm rounded-full border transition ${
                  active
                    ? "bg-saffron-500 text-white border-saffron-500"
                    : "bg-white border-ink-200 hover:border-saffron-500"
                }`}
              >
                {s}
              </button>
            );
          })}
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-ink-700 mb-1">
          Special instructions <span className="text-ink-400 font-normal">(free form)</span>
        </label>
        <textarea
          value={specialInstructions}
          onChange={(e) => setSpecialInstructions(e.target.value)}
          rows={3}
          placeholder="e.g. pure vegetarian, two seniors who can't walk long, avoid crowded temples, prefer boutique homestays"
          className="w-full px-3 py-2 border border-ink-200 rounded-lg bg-white focus:outline-none focus:border-saffron-500"
        />
      </div>

      <button
        onClick={handleSubmit}
        disabled={loading || !destination.trim()}
        className="w-full py-3 rounded-lg bg-ink-900 text-ink-50 font-medium hover:bg-ink-800 disabled:opacity-50 disabled:cursor-not-allowed transition"
      >
        {loading ? "Researching & planning… (takes 30–90s)" : "Generate itinerary"}
      </button>
    </div>
  );
}
