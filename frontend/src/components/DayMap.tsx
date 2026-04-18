"use client";

import L from "leaflet";
import { MapContainer, Marker, Polyline, Popup, TileLayer } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import type { Activity, DayPlan, MealSuggestion } from "@/lib/types";

// Build a small numbered marker icon. Leaflet's default icon paths break under
// bundlers; since we're drawing our own HTML icon anyway, we avoid the whole
// problem.
function numberedIcon(label: string, color: string) {
  return L.divIcon({
    className: "",
    html: `<div style="
      background:${color};
      color:white;
      width:28px;height:28px;
      border-radius:50%;
      display:flex;align-items:center;justify-content:center;
      font-weight:600;font-size:13px;
      border:2px solid white;
      box-shadow:0 1px 3px rgba(0,0,0,0.35);
    ">${label}</div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
}

type Pin = {
  lat: number;
  lng: number;
  label: string;
  title: string;
  subtitle?: string;
  color: string;
};

function pinsForDay(day: DayPlan): Pin[] {
  const pins: Pin[] = [];
  let n = 1;
  const pushAct = (a: Activity) => {
    if (a.lat == null || a.lng == null) return;
    pins.push({
      lat: a.lat,
      lng: a.lng,
      label: String(n++),
      title: a.name,
      subtitle: a.location,
      color: "#E07A2B", // saffron — matches UI accent
    });
  };
  day.morning.forEach(pushAct);
  day.afternoon.forEach(pushAct);
  day.evening.forEach(pushAct);
  // Meals get a different color so the route visualization doesn't treat
  // them as just another sightseeing stop.
  day.meals.forEach((m: MealSuggestion) => {
    if (m.lat == null || m.lng == null) return;
    pins.push({
      lat: m.lat,
      lng: m.lng,
      label: mealEmoji(m.meal),
      title: m.place,
      subtitle: `${m.meal} · ${m.cuisine}`,
      color: "#6B7280", // muted gray so meals are visible but secondary
    });
  });
  return pins;
}

function mealEmoji(meal: MealSuggestion["meal"]): string {
  switch (meal) {
    case "breakfast":
      return "☕";
    case "lunch":
      return "🍽";
    case "dinner":
      return "🍲";
    default:
      return "🥨";
  }
}

interface Props {
  day: DayPlan;
}

export default function DayMap({ day }: Props) {
  const pins = pinsForDay(day);
  if (pins.length < 2) return null; // single-pin map is just a dot

  // Route polyline traces the *ordered* sightseeing stops. Meals are plotted
  // but intentionally not part of the line — they'd zig-zag it.
  const routePoints: [number, number][] = pins
    .filter((p) => /^\d+$/.test(p.label))
    .map((p) => [p.lat, p.lng]);

  const lats = pins.map((p) => p.lat);
  const lngs = pins.map((p) => p.lng);
  const bounds: L.LatLngBoundsExpression = [
    [Math.min(...lats), Math.min(...lngs)],
    [Math.max(...lats), Math.max(...lngs)],
  ];

  return (
    <div className="rounded-lg overflow-hidden border border-ink-200 h-64 mb-4">
      <MapContainer
        bounds={bounds}
        boundsOptions={{ padding: [30, 30] }}
        style={{ height: "100%", width: "100%" }}
        scrollWheelZoom={false}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {routePoints.length >= 2 && (
          <Polyline positions={routePoints} pathOptions={{ color: "#E07A2B", weight: 3, opacity: 0.6 }} />
        )}
        {pins.map((p, i) => (
          <Marker key={i} position={[p.lat, p.lng]} icon={numberedIcon(p.label, p.color)}>
            <Popup>
              <div className="font-medium">{p.title}</div>
              {p.subtitle && <div className="text-xs text-ink-500">{p.subtitle}</div>}
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
