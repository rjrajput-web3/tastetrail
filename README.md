# TasteTrail — Agentic Taste Trip Planner

**Qloo Agentic Hackathon submission** · by Rohit Rajput

Tell TasteTrail a city and what you love. An agent loop resolves your interests
into Qloo taste-graph tags, queries live cultural affinities across places,
destinations and artists, then curates a full day plan — with per-pick
explanations of *why* each recommendation matches your taste.

## How it works (the agent)

1. **Planner** — splits the request: taste-tag resolution → place insights →
   destination insights → artist insights.
2. **TasteTools** — calls the Qloo Taste AI hackathon API:
   - `GET /v2/tags` turns free-text interests ("street food", "indie music") into tag IDs
   - `GET /v2/insights` with `filter.type=urn:entity:place` + `filter.location.query=<city>`
     + `signal.interests.tags` returns taste-matched venues, `feature.explainability=true`
     adds per-recommendation attribution
   - same endpoint with `urn:entity:destination` (day-trip ideas) and
     `urn:entity:artist` (trip soundtrack)
3. **Curator** — buckets venues into morning / afternoon / evening / night and
   renders the plan with affinity scores and taste explanations.

Every recommendation is genuinely computed from the Qloo cultural graph —
no hardcoded lists, no mock data.

## Run locally

```bash
export QLOO_API_KEY="<your hackathon key>"
python3 -m http.server 8000        # serves index.html
# api/plan.py runs as a serverless function on Vercel; for local API testing
# use `vercel dev`
```

## Deploy (Vercel)

1. Push this repo to GitHub (`rjrajput-web3/tastetrail`).
2. Import into Vercel (auto-detects `api/plan.py` as a serverless function).
3. Add env var `QLOO_API_KEY` in Vercel project settings (never commit the key).

## Submission checklist

- [ ] Hosted demo URL (Vercel)
- [ ] Public GitHub repo with MIT license
- [ ] Devpost text description (below)

**Devpost description:** TasteTrail is an agentic trip planner built on the Qloo
Taste AI cultural graph. Enter any city plus your interests; the agent resolves
your taste into graph tags and returns a full day plan — venues bucketed by
time of day, day-trip ideas, and a soundtrack — each pick explained by live
taste-affinity scores. Built for travelers who want plans that feel like *them*.

## License

MIT — see LICENSE.
