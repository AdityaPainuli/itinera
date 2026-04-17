"use client";

import type { Activity, Itinerary } from "@/lib/types";

function formatINR(n: number): string {
  return `₹${n.toLocaleString("en-IN")}`;
}

function buildMapHref(lat?: number, lng?: number): string | null {
  if (
    typeof lat !== "number" ||
    typeof lng !== "number" ||
    !Number.isFinite(lat) ||
    !Number.isFinite(lng)
  ) {
    return null;
  }
  const params = new URLSearchParams({ api: "1", query: `${lat},${lng}` });
  return `https://www.google.com/maps/search/?${params.toString()}`;
}

function ActivityCard({ a }: { a: Activity }) {
  const mapHref = buildMapHref(a.lat, a.lng);
  return (
    <div className="border-l-2 border-saffron-500 pl-3 py-1">
      <div className="flex items-baseline justify-between gap-3">
        <div className="font-medium text-ink-900">{a.name}</div>
        <div className="text-xs text-ink-500 whitespace-nowrap">
          {a.duration_minutes} min · {formatINR(a.cost_inr)}
        </div>
      </div>
      <div className="text-sm text-ink-600">
        {a.location}
        {a.neighborhood && <span className="text-ink-500"> · {a.neighborhood}</span>}
        {mapHref && (
          <>
            {" · "}
            <a
              href={mapHref}
              target="_blank"
              rel="noopener noreferrer"
              className="text-saffron-700 underline"
            >
              map
            </a>
          </>
        )}
      </div>
      <div className="text-sm text-ink-700 mt-1">{a.description}</div>
      {a.tips && <div className="text-xs italic text-ink-500 mt-1">Tip: {a.tips}</div>}
    </div>
  );
}

interface Props {
  itinerary: Itinerary;
  onExportMarkdown?: () => void;
  onExportJson?: () => void;
}

export function ItineraryDisplay({ itinerary: it, onExportMarkdown, onExportJson }: Props) {
  const req = it.request;
  const cb = it.cost_breakdown;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-serif text-3xl text-ink-900">
            {req.destination} · {req.duration_days} days
          </h1>
          <div className="text-ink-500 text-sm mt-1">
            {req.travelers} traveler{req.travelers > 1 ? "s" : ""} · budget {formatINR(req.budget_inr)}
          </div>
        </div>
        <div className="flex gap-2">
          {onExportMarkdown && (
            <button
              onClick={onExportMarkdown}
              className="px-3 py-1.5 text-sm border border-ink-200 rounded-lg bg-white hover:border-saffron-500"
            >
              ⬇ Markdown
            </button>
          )}
          {onExportJson && (
            <button
              onClick={onExportJson}
              className="px-3 py-1.5 text-sm border border-ink-200 rounded-lg bg-white hover:border-saffron-500"
            >
              ⬇ JSON
            </button>
          )}
        </div>
      </div>

      <section className="bg-white border border-ink-200 rounded-xl p-5">
        <p className="text-ink-700 leading-relaxed">{it.summary}</p>
        <div className="grid md:grid-cols-3 gap-4 mt-4 text-sm">
          <div>
            <div className="text-xs uppercase tracking-wide text-ink-500">Best time</div>
            <div className="text-ink-700">{it.best_time_to_visit}</div>
          </div>
          <div>
            <div className="text-xs uppercase tracking-wide text-ink-500">Getting there</div>
            <div className="text-ink-700">{it.getting_there}</div>
          </div>
          <div>
            <div className="text-xs uppercase tracking-wide text-ink-500">Local transport</div>
            <div className="text-ink-700">{it.local_transportation}</div>
          </div>
        </div>
      </section>

      <section>
        <h2 className="font-serif text-2xl text-ink-900 mb-3">Day by day</h2>
        <div className="space-y-4">
          {it.days.map((d) => (
            <div key={d.day_number} className="bg-white border border-ink-200 rounded-xl p-5">
              <div className="flex items-baseline justify-between mb-1 flex-wrap gap-2">
                <h3 className="font-serif text-xl text-ink-900">
                  Day {d.day_number} — {d.theme}
                </h3>
                <span className="text-sm text-ink-500">
                  ~{formatINR(d.daily_cost_estimate_inr)}
                </span>
              </div>
              {(d.base_area || d.route_notes) && (
                <div className="text-xs text-ink-500 mb-3">
                  {d.base_area && <span className="font-medium text-ink-600">📍 {d.base_area}</span>}
                  {d.base_area && d.route_notes && <span> · </span>}
                  {d.route_notes && <span>{d.route_notes}</span>}
                </div>
              )}
              {(["morning", "afternoon", "evening"] as const).map((bucket) => {
                const items = d[bucket];
                if (!items || items.length === 0) return null;
                return (
                  <div key={bucket} className="mb-4">
                    <div className="text-xs uppercase tracking-wide text-ink-500 mb-2">
                      {bucket}
                    </div>
                    <div className="space-y-3">
                      {items.map((a, i) => (
                        <ActivityCard key={i} a={a} />
                      ))}
                    </div>
                  </div>
                );
              })}
              {d.meals.length > 0 && (
                <div>
                  <div className="text-xs uppercase tracking-wide text-ink-500 mb-2">Meals</div>
                  <ul className="text-sm text-ink-700 space-y-1">
                    {d.meals.map((m, i) => (
                      <li key={i}>
                        <span className="capitalize text-ink-500">{m.meal}:</span>{" "}
                        <span className="font-medium">{m.place}</span> · {m.cuisine} ·{" "}
                        {formatINR(m.cost_inr)}
                        {m.notes && <span className="text-ink-500"> — {m.notes}</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="font-serif text-2xl text-ink-900 mb-3">Where to stay</h2>
        <div className="grid md:grid-cols-2 gap-3">
          {it.accommodation_suggestions.map((a, i) => (
            <div key={i} className="bg-white border border-ink-200 rounded-xl p-4">
              <div className="flex items-baseline justify-between">
                <div className="font-medium text-ink-900">{a.name}</div>
                <div className="text-sm text-ink-500">
                  {formatINR(a.price_per_night_inr)}/night
                </div>
              </div>
              <div className="text-sm text-ink-500">
                {a.type} · {a.area}
                {a.rating && <> · ⭐ {a.rating}</>}
              </div>
              <div className="text-sm text-ink-700 mt-2">{a.why}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="bg-white border border-ink-200 rounded-xl p-5">
        <h2 className="font-serif text-xl text-ink-900 mb-3">Cost breakdown</h2>
        <table className="w-full text-sm">
          <tbody>
            <tr className="border-b border-ink-100">
              <td className="py-1.5">Accommodation</td>
              <td className="py-1.5 text-right">{formatINR(cb.accommodation_inr)}</td>
            </tr>
            <tr className="border-b border-ink-100">
              <td className="py-1.5">Food</td>
              <td className="py-1.5 text-right">{formatINR(cb.food_inr)}</td>
            </tr>
            <tr className="border-b border-ink-100">
              <td className="py-1.5">Activities</td>
              <td className="py-1.5 text-right">{formatINR(cb.activities_inr)}</td>
            </tr>
            <tr className="border-b border-ink-100">
              <td className="py-1.5">Transport</td>
              <td className="py-1.5 text-right">{formatINR(cb.transport_inr)}</td>
            </tr>
            <tr className="border-b border-ink-100">
              <td className="py-1.5">Miscellaneous</td>
              <td className="py-1.5 text-right">{formatINR(cb.miscellaneous_inr)}</td>
            </tr>
            <tr className="font-semibold">
              <td className="pt-2">Total</td>
              <td className="pt-2 text-right">{formatINR(cb.total_inr)}</td>
            </tr>
          </tbody>
        </table>
        <div className={`mt-3 text-sm ${cb.fits_budget ? "text-green-700" : "text-amber-700"}`}>
          {cb.fits_budget ? "✓ Fits your budget" : "⚠ Exceeds your stated budget"}
        </div>
        {cb.computed_total_inr != null && cb.computed_total_inr !== cb.total_inr && (
          <div className="mt-2 text-xs text-ink-500">
            Verified sum from per-item costs:{" "}
            <span className="font-medium text-ink-700">
              {formatINR(cb.computed_total_inr)}
            </span>{" "}
            (model reported {formatINR(cb.total_inr)})
          </div>
        )}
        {cb.notes && <div className="mt-2 text-sm text-ink-600 italic">{cb.notes}</div>}
      </section>

      {it.quality_checks && it.quality_checks.length > 0 && (
        <section className="bg-ink-100 rounded-xl p-4">
          <details>
            <summary className="cursor-pointer text-sm font-medium text-ink-700">
              Quality checks ({it.quality_checks.length})
            </summary>
            <ul className="mt-2 text-xs text-ink-600 space-y-1 list-disc pl-5">
              {it.quality_checks.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          </details>
        </section>
      )}

      <div className="grid md:grid-cols-2 gap-4">
        {it.packing_list.length > 0 && (
          <section className="bg-white border border-ink-200 rounded-xl p-5">
            <h2 className="font-serif text-xl text-ink-900 mb-3">Packing list</h2>
            <ul className="text-sm text-ink-700 space-y-1 list-disc pl-5">
              {it.packing_list.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          </section>
        )}
        {it.local_tips.length > 0 && (
          <section className="bg-white border border-ink-200 rounded-xl p-5">
            <h2 className="font-serif text-xl text-ink-900 mb-3">Local tips</h2>
            <ul className="text-sm text-ink-700 space-y-1 list-disc pl-5">
              {it.local_tips.map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ul>
          </section>
        )}
      </div>

      {it.cautions.length > 0 && (
        <section className="bg-amber-50 border border-amber-200 rounded-xl p-5">
          <h2 className="font-serif text-xl text-ink-900 mb-3">Cautions</h2>
          <ul className="text-sm text-ink-700 space-y-1 list-disc pl-5">
            {it.cautions.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </section>
      )}

      {it.sources.length > 0 && (
        <section>
          <details className="bg-ink-100 rounded-xl p-4">
            <summary className="cursor-pointer text-sm font-medium text-ink-700">
              Sources ({it.sources.length})
            </summary>
            <ul className="mt-2 text-xs text-ink-600 space-y-1">
              {it.sources.map((s, i) => (
                <li key={i} className="break-all">
                  <a href={s} target="_blank" rel="noreferrer" className="underline">
                    {s}
                  </a>
                </li>
              ))}
            </ul>
          </details>
        </section>
      )}
    </div>
  );
}
