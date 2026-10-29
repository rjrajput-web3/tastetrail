"""TasteTrail agent backend (Vercel serverless).

Agentic loop:
  1. Planner   - splits the user's request into sub-tasks (tags, places, destinations, artists)
  2. TasteTools - calls the Qloo Taste AI hackathon API (search/tags/insights)
  3. Curator   - ranks + buckets results into a day plan with taste explanations

Qloo API key is NEVER committed: it is read from the QLOO_API_KEY env var.
Local copy lives at:
  ~/workspace/goals/earn-70-000-90-000-per-month-online/hidden_files/qloo-api-key.txt
(kept chmod 600, never printed anywhere).
"""

from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.parse
import urllib.request

BASE = "https://hackathon.api.qloo.com"
TIMEOUT = 25


class QlooError(Exception):
    pass


def qloo_get(path, params):
    key = os.environ.get("QLOO_API_KEY", "").strip()
    if not key:
        raise QlooError("missing_api_key")
    qs = urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(
        f"{BASE}{path}?{qs}",
        headers={"X-Api-Key": key, "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:400]
        raise QlooError(f"http_{e.code}:{body}")


# ---------- TasteTools ----------

def resolve_tags(keywords):
    """Planner step 1: turn free-text interests into Qloo tag IDs."""
    tag_ids = []
    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue
        try:
            # /v2/tags query param is `filter.query` (docs: get-tags reference)
            data = qloo_get("/v2/tags", {"filter.query": kw, "take": 3})
            results = data.get("results", {}).get("tags", []) or data.get("results", [])
            for t in results[:2]:
                tid = t.get("id") or t.get("tag_id")
                if tid and tid not in tag_ids:
                    tag_ids.append(tid)
        except QlooError:
            continue
    return tag_ids[:6]


def insights(filter_type, params):
    base = {"filter.type": filter_type, "take": 8,
            "feature.explainability": "true"}
    base.update(params)
    data = qloo_get("/v2/insights", base)
    return data.get("results", {}).get("entities", []) or []


def get_places(city, tag_ids):
    params = {
        "filter.location.query": city,
        "filter.exists": "properties.description",
        "bias.quality": "medium",
    }
    if tag_ids:
        params["signal.interests.tags"] = ",".join(tag_ids)
    return insights("urn:entity:place", params)


def get_destinations(tag_ids):
    params = {}
    if tag_ids:
        params["signal.interests.tags"] = ",".join(tag_ids)
    return insights("urn:entity:destination", params)


def get_artists(tag_ids):
    params = {}
    if tag_ids:
        params["signal.interests.tags"] = ",".join(tag_ids)
    return insights("urn:entity:artist", params)


# ---------- Curator ----------

def entity_name(e):
    props = e.get("properties", {})
    return e.get("name") or props.get("name") or "Unknown"


def entity_desc(e):
    props = e.get("properties", {})
    d = props.get("description") or props.get("short_description") or ""
    return (d[:220] + "...") if len(d) > 220 else d


def entity_image(e):
    props = e.get("properties", {})
    img = props.get("image") or {}
    return img.get("url") if isinstance(img, dict) else (img or "")


def why_text(e):
    qx = e.get("query", {}).get("explainability", {})
    comps = qx.get("components") or []
    bits = []
    for c in comps[:2]:
        name = c.get("name") or c.get("entity", {}).get("name", "")
        score = c.get("score", 0)
        if name:
            bits.append(f"{name} ({score:.0%})")
    return "Taste match: " + ", ".join(bits) if bits else "Taste-graph match"


def bucket_places(places):
    buckets = {"morning": [], "afternoon": [], "evening": [], "night": []}
    for p in places:
        text = json.dumps(p.get("tags", [])).lower() + " " + (p.get("subtype") or "").lower()
        item = {
            "name": entity_name(p),
            "description": entity_desc(p),
            "image": entity_image(p),
            "why": why_text(p),
            "affinity": round((p.get("query") or {}).get("affinity", 0), 3),
        }
        if any(k in text for k in ["breakfast", "cafe", "coffee", "brunch", "bakery"]):
            buckets["morning"].append(item)
        elif any(k in text for k in ["bar", "nightclub", "club", "lounge", "cocktail"]):
            buckets["night"].append(item)
        elif any(k in text for k in ["dinner", "restaurant", "fine dining", "bistro"]):
            buckets["evening"].append(item)
        else:
            buckets["afternoon"].append(item)
    # cap at 3 per bucket, then fill empty buckets from the fullest one
    # so the demo always shows every time-of-day section
    for k in buckets:
        buckets[k] = sorted(buckets[k], key=lambda x: x["affinity"], reverse=True)
    for k in buckets:
        if not buckets[k]:
            donor = max(buckets, key=lambda d: len(buckets[d]))
            if len(buckets[donor]) > 1:
                buckets[k].append(buckets[donor].pop())
    for k in buckets:
        buckets[k] = buckets[k][:3]
    return buckets


def plan_trip(city, interests):
    tag_ids = resolve_tags(interests)
    try:
        places = get_places(city, tag_ids)
    except QlooError as e:
        if "http_400" in str(e):
            raise QlooError("unknown_city")
        raise
    destinations = get_destinations(tag_ids) if tag_ids else []
    artists = get_artists(tag_ids) if tag_ids else []

    def slim(ents, n=5):
        out = []
        for e in ents[:n]:
            out.append({
                "name": entity_name(e),
                "description": entity_desc(e),
                "image": entity_image(e),
                "why": why_text(e),
            })
        return out

    return {
        "city": city,
        "interests": interests,
        "day_plan": bucket_places(places),
        "day_trips": slim(destinations),
        "soundtrack": slim(artists),
        "taste_tags_used": len(tag_ids),
    }


# ---------- Vercel handler ----------

class handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            city = (body.get("city") or "").strip()
            interests = body.get("interests") or []
            if isinstance(interests, str):
                interests = [s.strip() for s in interests.split(",")]
            if not city:
                return self._send(400, {"error": "city is required"})
            result = plan_trip(city, [i for i in interests if i][:5])
            self._send(200, result)
        except QlooError as e:
            msg = str(e)
            if msg == "missing_api_key":
                self._send(500, {"error": "server misconfigured"})
            elif msg == "unknown_city":
                self._send(400, {"error": "city not recognized - try a larger nearby city"})
            else:
                self._send(502, {"error": "taste engine unavailable, try again"})
        except Exception:
            self._send(500, {"error": "unexpected error"})
