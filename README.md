# Itinera

AI-generated travel itineraries with live web research. Give it a destination, budget, and any weird constraints you have — it searches the web for current attractions, hotel prices, and logistics, then produces a concrete day-by-day plan with cost breakdown, packing list, and local tips.

![status](https://img.shields.io/badge/status-alpha-orange)

## What it does

- **Research-grounded** — Uses Claude's server-side `web_search` tool to pull current info (prices, hours, closures) rather than hallucinating from stale training data.
- **Structured output** — Typed itinerary with days, activities, meals, accommodations, cost breakdown, packing list, cautions, and source URLs.
- **Budget-aware** — Respects the INR budget you set; flags clearly when it can't fit.
- **Free-form constraints** — "Pure veg, 2 seniors who can't walk long, avoid crowded temples" just works.
- **History + export** — Everything persists to SQLite; export as Markdown or JSON.

## Stack

| Layer    | Tech                                                                 |
|----------|----------------------------------------------------------------------|
| Backend  | Python 3.11+, FastAPI, Anthropic SDK, SQLAlchemy async, SQLite       |
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind                        |
| Agent    | Single-turn with `web_search_20250305` tool, structured JSON output  |

## Quickstart

### 1. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # then edit .env and set ANTHROPIC_API_KEY
uvicorn app.main:app --reload --port 8000
```

Sanity check: `curl http://localhost:8000/health` should return `{"status":"ok"}`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000.

## Project structure

```
itinera/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry
│   │   ├── config.py            # settings (env-driven)
│   │   ├── schemas.py           # Pydantic models (shared shape)
│   │   ├── database.py          # SQLAlchemy async + SQLite
│   │   ├── agents/
│   │   │   ├── itinerary_agent.py  # wraps Anthropic + web_search
│   │   │   └── prompts.py          # system + user prompts
│   │   └── api/routes.py        # REST endpoints
│   └── requirements.txt
└── frontend/
    └── src/
        ├── app/                 # Next.js pages
        ├── components/          # Form, Display, History
        └── lib/                 # API client + shared types
```

## API

| Method | Path                                     | Purpose                          |
|--------|------------------------------------------|----------------------------------|
| POST   | `/api/itinerary/generate`                | Run the agent, return itinerary  |
| GET    | `/api/itinerary`                         | List past itineraries            |
| GET    | `/api/itinerary/{id}`                    | Get one                          |
| GET    | `/api/itinerary/{id}/markdown`           | Export as markdown               |
| DELETE | `/api/itinerary/{id}`                    | Delete                           |

OpenAPI docs at http://localhost:8000/docs.

## Cost notes

Each generation makes one Claude API call with `web_search` enabled (default cap: 6 searches). Expect a few cents per itinerary on Opus — cheaper on Sonnet. Adjust `ANTHROPIC_MODEL` and `MAX_WEB_SEARCHES` in `.env`.

## Roadmap ideas

- Streaming the agent's "I'm researching X now" progress via SSE
- Multi-city optimizer (pick best route order given lat/lng)
- Real-time flight/train price lookup via separate tools
- Group planning: invite others, vote on activities
- Map view with day routes (the Google Places tool pairs well here)
- Swap SQLite → Postgres + pgvector for "find similar past trips" search

## License

MIT
