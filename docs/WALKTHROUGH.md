# Loom walkthrough script (about 7 minutes)

A suggested outline for the 5–10 minute video. Times are approximate.

## 1. The problem and the result (0:00–0:45)
- "A driver enters a trip; the app compares three routes using the forecast at the time the truck will be at each point, and recommends the safest one."
- Show the finished screen: recommendation box, three route cards, map with coloured routes and the heatmap.

## 2. Planning a trip (0:45–2:00)
- Type an origin and destination (show the autocomplete), set the departure time and load weight (e.g. 42,000 lb).
- Choose a 10, 25 or 50 mile sample interval. Optionally tick hours-of-service.
- Press **Find safest route**. Point out the three routes and that the recommended one is pre-selected.

## 3. Risk and recommendation logic (2:00–3:45)
- Hover a checkpoint on the map: ETA, wind/gusts, rain, snow, level, and *why* (e.g. "Wind 40 mph with 42,000 lb load").
- Show the checkpoint table; click a row to fly the map to it.
- Open **How routes are ranked**: No Travel miles → Severe → High → average risk → time. Each checkpoint covers the road halfway to its neighbours, so risk miles add up to the route length.
- Read the "vs Route B: …" explanations.
- Mention boundary handling (0.25 in/hr is High, 30,000 lb exactly is not "over 30,000").
- Change the load to 30,001+ / 40,001+ lb on a windy day to show the load rules change the result.

## 4. Heatmap and time slider (3:45–5:15)
- Drag the 0–48 h slider; the trucks move along their routes and the heatmap updates instantly.
- Press play. Switch layers: Risk, Wind, Gusts, Rain, Snow; the colour stops match the risk thresholds.
- Explain the performance design: the corridor grid is fetched once, frames are rendered once, cached and pre-rendered, and the slider only swaps an image on the GPU.

## 5. Code tour (5:15–6:45)
- `backend/planner/domain/`: pure, tested logic (risk.py, checkpoints.py, recommend.py, hos.py).
- `backend/planner/services/`: routing (Valhalla truck + via-point alternatives), weather (batching, caching, ETA sampling), heatmap.
- `frontend/src/lib/heatmapRaster.ts` and `truck.ts`; `components/MapView.tsx`.
- Run the tests: `pytest` (91 tests) and `npm test`.

## 6. Wrap-up (6:45–7:15)
- Deployment: one Docker image on Render (Blueprint in `render.yaml`).
- Trade-offs: sustained wind is scored and gusts are informational; HOS is simplified; free API rate limits.

Tip: for the demo, pick a region with active weather (check the Wind/Rain layers, or windy.com) so the routes differ in risk.
