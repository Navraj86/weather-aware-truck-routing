# Weather-Aware Truck Routing

A React + Django web app that helps a truck driver pick the safest route. It
compares three route options, checks the forecast at every checkpoint **at the
time the truck will actually be there**, classifies the risk using the
assessment's weather and load rules, and recommends a route.

**Live demo:** https://weather-aware-truck-routing-fnis.onrender.com

> Hosted on Render's free plan: if nobody has opened it for 15 minutes, the first load takes about a minute while it wakes up.

## Features

- Origin and destination search (autocomplete, or type `lat, lon`), departure time, load weight.
- **Three route options** from a truck routing profile (Valhalla, using the load weight). If the router returns fewer than three distinct routes, more are generated through via points on either side of the main route.
- **Checkpoints every 10, 25 or 50 miles**, each with an ETA from the route's own speed profile.
- **Forecast at each checkpoint's ETA**: wind, gusts, rain and snow from Open-Meteo hourly data.
- **Risk classification** using the assessment's thresholds and load rules, with the reasons ("Wind 48 mph with 42,000 lb load").
- **Recommendation** using the specified order (fewest Severe miles, then High miles, then average risk, then travel time), with a plain-language explanation of why it beats each alternative.
- **Map**: every route coloured by risk, checkpoint markers with ETA/weather popups, route labels, endpoints, and HOS stops.
- **Weather heatmap** along the trip corridor with a **0–48 h slider** (play/pause), layers for risk, wind, gusts, rain and snow, and truck markers showing where each truck would be at the selected time.
- Optional **hours-of-service stops** (30 min after 8 h of driving, 10 h rest after 11 h), which shift every downstream ETA.

## How it works

```
origin, destination, departure, load
        │
        ▼
Valhalla truck routing (3 routes, with shape + per-maneuver time)
        │
        ▼
checkpoints every N miles ──► ETA = departure + drive time to that mile (+ HOS stops)
        │
        ▼
Open-Meteo hourly forecast (batched, de-duplicated, cached) sampled at each ETA
        │
        ▼
risk per checkpoint ──► risk miles per route ──► recommendation
```

### Risk rules

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind | < 25 mph | 25–34 | 35–44 | 45–54 | ≥ 55 mph |
| Rain | < 0.10 in/hr | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | > 1.00 |
| Snow | < 0.5 in/hr | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | > 3.0 |

Load rules: wind ≥ 55 mph is No Travel for any load; wind 45–54 mph with a load over 30,000 lb is No Travel; wind 35–44 mph with a load over 40,000 lb is Severe.
A checkpoint's level is the **worst** of the wind, rain, snow and load rules.

Boundary handling, since the ranges in the spec share endpoints:
- Each band includes its lower bound, so 0.25 in/hr of rain is High and 35 mph wind is High.
- The top band starts strictly above 1.00 in/hr rain and 3.0 in/hr snow, as written (`>`).
- Wind bands are whole mph, so 34.9 mph is Moderate.
- "Over 30,000 lb" means strictly more than 30,000.

All of this lives in [`backend/planner/domain/risk.py`](backend/planner/domain/risk.py) and is tested at every boundary in [`tests/test_risk.py`](backend/tests/test_risk.py).

### Weather at the truck's arrival time

- Valhalla returns per-maneuver travel times. Each maneuver's time is spread over its shape points in proportion to distance, which gives a cumulative drive time at every point of the route. A checkpoint's ETA is the departure time plus the drive time to that mile, plus any HOS stops taken before it.
- Open-Meteo reports **rain, showers and snowfall as the total for the preceding hour**, which is an in/hr rate. A checkpoint therefore uses the hour that contains its ETA. Rain intensity is `rain + showers`.
- **Wind** is an instantaneous value, so it is interpolated linearly between hours. The risk rules use sustained 10 m wind; gusts are shown for reference only.
- Forecast points are snapped to a 0.05° grid (~3.5 mi, finer than the forecast models) so overlapping routes share requests. Requests are batched (100 locations per call), retried with backoff, and cached for an hour. Request windows come in fixed lengths, so trips planned in the same hour reuse the cache.

### Route recommendation

Each checkpoint represents the road halfway to its neighbouring checkpoints, so the "risk miles" of a route add up to exactly its length. Routes are then ranked by:

0. fewest **No Travel** miles. This is a safety guard: No Travel is worse than Severe, so it is checked first.
1. fewest **Severe** miles (Severe + No Travel)
2. fewest **High** miles
3. lowest **distance-weighted average risk** (Low = 0 … No Travel = 4)
4. shortest **travel time**

Miles are compared to 0.1 mi and the average to 0.01, so floating-point noise never outweighs a real difference further down the list. If even the best route has No Travel or Severe stretches, the UI shows a warning.

### Heatmap performance

- The backend builds a grid that is regular in **Web Mercator** over the trip's bounding box. It only fetches cells within a corridor around the routes (≤ 200 cells) and returns 49–50 hourly frames for every layer in one response.
- The browser upsamples the grid with bilinear interpolation. Cells with no data get zero weight, so values stay accurate at the edges and the heatmap fades out softly at the corridor boundary.
- The pixel-to-cell weights are computed once. Each frame is rendered to a PNG once, cached, and pre-rendered during idle time. Moving the slider only swaps the image on a MapLibre `image` source, so scrubbing and playback never re-fetch or re-compute.

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | React 18, TypeScript, Vite, MapLibre GL JS (WebGL), OpenFreeMap vector tiles |
| Backend | Django 5.2 + Django REST Framework, `requests`, WhiteNoise, Gunicorn |
| Routing | [Valhalla](https://valhalla.github.io/valhalla/) public server, `truck` costing with the load weight (OSRM fallback) |
| Weather | [Open-Meteo](https://open-meteo.com/) hourly forecast (wind, gusts, rain, showers, snowfall, weather code) |
| Geocoding | [Photon](https://photon.komoot.io/) (OpenStreetMap) |

None of the services need an API key.

## Project layout

```
backend/
  config/                 Django settings & URLs
  planner/
    domain/               pure logic, no I/O
      risk.py             thresholds + load rules
      checkpoints.py      checkpoint placement, ETA, risk aggregation
      recommend.py        ranking + explanations
      hos.py              hours-of-service clock
      geo.py              polyline maths, Douglas-Peucker, mercator
    services/             third-party APIs and orchestration
      routing.py          Valhalla/OSRM, alternatives, de-duplication
      weather.py          Open-Meteo batching, caching, time sampling
      heatmap.py          corridor grid, 0-48 h frames
      planner.py          end-to-end trip planning
    views.py, serializers.py
  tests/                  91 pytest tests (domain, services with fakes, API)
frontend/
  src/
    components/           TripForm, PlaceInput, RoutePanel, CheckpointTable, MapView, TimeControls
    lib/                  heatmapRaster.ts, truck.ts, risk.ts, format.ts (+ vitest tests)
    api.ts, types.ts, App.tsx
Dockerfile, render.yaml
```

## API

| Method | Path | Body / query | Returns |
|---|---|---|---|
| `GET` | `/api/geocode?q=denver` | | `{results: [{label, lat, lon}]}` |
| `POST` | `/api/plan` | `{origin:{lat,lon}, destination:{lat,lon}, departure: ISO-8601, load_lb, interval_mi: 10\|25\|50, hos: bool}` | routes (geometry, checkpoints with weather + risk, risk segments, HOS stops, summary) and the recommendation |
| `POST` | `/api/heatmap` | `{corridors: [[[lat,lon],…]], departure, load_lb}` | grid bounds, cell list, hourly times, `layers.{risk,wind,gust,rain,snow}[hour][cell]` |
| `GET` | `/api/health` | | `{status: "ok"}` |

Departure must be within the next 7 days (forecast range). Validation errors return HTTP 400 with field messages. A failing third-party service returns 502/503 with `{error, service}`.

## Running locally

Requirements: Python 3.12+ and Node 20+.

```bash
# Backend (http://127.0.0.1:8000)
cd backend
python -m venv .venv
.venv/Scripts/activate            # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements-dev.txt
DJANGO_DEBUG=1 python manage.py runserver
```

```bash
# Frontend dev server with hot reload (http://localhost:5173, proxies /api to :8000)
cd frontend
npm install
npm run dev
```

Production-style, single server: run `npm run build` in `frontend/`, then start Django. It serves `frontend/dist` at `/`.

Tests:

```bash
cd backend && pytest          # 91 tests
cd frontend && npm test       # vitest
cd frontend && npm run typecheck
```

## Deployment

The repo ships a multi-stage `Dockerfile`: it builds the React app, then runs Django + Gunicorn and serves the built app with WhiteNoise. It deploys as **one service**.

**Render (free tier):** New → Blueprint → select this repo. `render.yaml` creates the web service, generates `DJANGO_SECRET_KEY` and allows `*.onrender.com`.

**Anywhere with Docker:**

```bash
docker build -t truck-routing .
docker run -p 8000:8000 -e DJANGO_SECRET_KEY=change-me -e DJANGO_ALLOWED_HOSTS=localhost truck-routing
```

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | required unless `DJANGO_DEBUG=1` | Django secret |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | comma-separated hosts (`.example.com` for subdomains) |
| `DJANGO_DEBUG` | `0` | debug mode |
| `OPEN_METEO_API_KEY` | – | optional commercial key (higher rate limits) |
| `VALHALLA_URL`, `OSRM_URL`, `OPEN_METEO_URL`, `PHOTON_URL` | public servers | point at self-hosted instances |
| `PLAN_RATE_LIMIT`, `GEOCODE_RATE_LIMIT` | `20/min`, `120/min` | per-client throttling |

## Assumptions and limitations

- **Wind** means sustained 10 m wind speed. Gusts are displayed but not scored, because the spec gives one wind threshold.
- **Rain** = Open-Meteo `rain + showers` (liquid). **Snow** = `snowfall` depth per hour.
- Travel times come from Valhalla's truck profile and do not model traffic. HOS uses a simplified rule set (no 14-hour window or 70-hour cycle) and is off by default.
- The free Open-Meteo tier allows about 600 location-requests per minute per IP. A plan at a 10-mile interval on a long trip uses a few hundred. Retries and caching absorb most bursts; set `OPEN_METEO_API_KEY` for heavy use.
- The cache is in-process memory. Gunicorn runs one process with 8 threads so all requests share it.
- The public Valhalla/OSRM/Photon servers are community-run. All their URLs can be configured.
