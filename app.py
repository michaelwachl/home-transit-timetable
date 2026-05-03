from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import yaml
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


app = FastAPI(title="Home Transit Board")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

MVG_BASE = "https://www.mvg.de/api/fib/v2"
WEATHER_BASE = "https://api.open-meteo.com/v1"
TZ = ZoneInfo("Europe/Berlin")

# MVG transport type → fallback colour
TRANSPORT_COLORS: dict[str, str] = {
    "UBAHN": "#0065a3",
    "SBAHN": "#008d4f",
    "TRAM": "#d82020",
    "BUS": "#e87722",
    "REGIONAL_BUS": "#e87722",
    "BAHN": "#c0392b",
}

# Per-line colour overrides for Munich U-Bahn
UBAHN_LINE_COLORS: dict[str, str] = {
    "U1": "#4dab4d",
    "U2": "#c0272d",
    "U3": "#f47216",
    "U4": "#00a984",
    "U5": "#b4700a",
    "U6": "#0065a3",
    "U7": "#0065a3",
    "U8": "#0065a3",
}

# WMO weather code → (description, emoji)
WMO_MAP: dict[int, tuple[str, str]] = {
    0:  ("Clear",            "☀"),
    1:  ("Mostly Clear",     "🌤"),
    2:  ("Partly Cloudy",    "⛅"),
    3:  ("Overcast",         "☁"),
    45: ("Fog",              "🌫"),
    48: ("Icy Fog",          "🌫"),
    51: ("Light Drizzle",    "🌦"),
    53: ("Drizzle",          "🌦"),
    55: ("Heavy Drizzle",    "🌦"),
    61: ("Light Rain",       "🌧"),
    63: ("Rain",             "🌧"),
    65: ("Heavy Rain",       "🌧"),
    71: ("Light Snow",       "🌨"),
    73: ("Snow",             "🌨"),
    75: ("Heavy Snow",       "❄"),
    77: ("Snow Grains",      "❄"),
    80: ("Light Showers",    "🌦"),
    81: ("Showers",          "🌦"),
    82: ("Heavy Showers",    "🌧"),
    85: ("Snow Showers",     "🌨"),
    86: ("Heavy Snow Showers","❄"),
    95: ("Thunderstorm",     "⛈"),
    96: ("Thunderstorm+Hail","⛈"),
    99: ("Thunderstorm+Hail","⛈"),
}


# ── Transit ───────────────────────────────────────────────────────────────────

async def fetch_departures(client: httpx.AsyncClient, stop: dict) -> dict:
    global_id = stop["global_id"]
    limit = stop.get("max_departures", 10)
    lines_filter = set(stop.get("lines") or [])

    try:
        r = await client.get(
            f"{MVG_BASE}/departure",
            params={"globalId": global_id, "limit": limit * 3, "offsetInMinutes": 0},
            timeout=8,
        )
        r.raise_for_status()
        raw = r.json()
    except Exception as e:
        log.warning("MVG error for %s: %s", global_id, e)
        return {"stop": stop.get("name", global_id), "departures": [], "error": str(e)}

    now_ms = datetime.now(tz=timezone.utc).timestamp() * 1000
    items = raw if isinstance(raw, list) else raw.get("departures", [])
    departures: list[dict] = []

    for d in items:
        if d.get("cancelled"):
            continue
        label = d.get("label", "?")
        if lines_filter and label not in lines_filter:
            continue

        planned_ms = d.get("plannedDepartureTime", 0)
        realtime_ms = d.get("realtimeDepartureTime") or planned_ms
        delay = int(d.get("delayInMinutes") or 0)
        transport_type = d.get("transportType", "BUS")
        color = UBAHN_LINE_COLORS.get(label) or TRANSPORT_COLORS.get(transport_type, "#666666")

        departures.append({
            "line": label,
            "destination": d.get("destination", ""),
            "realtime_ms": int(realtime_ms),
            "delay": delay,
            "type": transport_type,
            "color": color,
            "platform": d.get("platform", ""),
        })

    departures.sort(key=lambda x: x["realtime_ms"])
    return {"stop": stop.get("name", global_id), "departures": departures[:limit], "error": None}


# ── Weather ───────────────────────────────────────────────────────────────────

async def fetch_weather(client: httpx.AsyncClient, cfg: dict) -> dict:
    wcfg = cfg["weather"]
    try:
        r = await client.get(
            f"{WEATHER_BASE}/forecast",
            params={
                "latitude": wcfg["latitude"],
                "longitude": wcfg["longitude"],
                "current": ",".join([
                    "temperature_2m",
                    "weather_code",
                    "wind_speed_10m",
                    "relative_humidity_2m",
                    "apparent_temperature",
                ]),
                "hourly": "temperature_2m,weather_code,precipitation_probability",
                "timezone": "Europe/Berlin",
                "forecast_days": 2,
            },
            timeout=8,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning("Weather error: %s", e)
        return {"error": str(e)}

    current = data.get("current", {})
    hourly = data.get("hourly", {})
    now = datetime.now(tz=TZ)

    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    codes = hourly.get("weather_code", [])
    precip = hourly.get("precipitation_probability", [])

    forecast: list[dict] = []
    for i, t in enumerate(times):
        dt = datetime.fromisoformat(t).replace(tzinfo=TZ)
        if dt <= now:
            continue
        if len(forecast) >= 12:
            break
        code = int(codes[i]) if i < len(codes) else 0
        desc, icon = WMO_MAP.get(code, ("Unknown", "?"))
        forecast.append({
            "time": dt.strftime("%H:%M"),
            "temp": round(temps[i]) if i < len(temps) else 0,
            "description": desc,
            "icon": icon,
            "precip_prob": int(precip[i]) if i < len(precip) else 0,
        })

    code = int(current.get("weather_code", 0))
    desc, icon = WMO_MAP.get(code, ("Unknown", "?"))

    return {
        "location": wcfg.get("location_name", ""),
        "current": {
            "temp": round(current.get("temperature_2m", 0)),
            "feels_like": round(current.get("apparent_temperature", 0)),
            "humidity": int(current.get("relative_humidity_2m", 0)),
            "wind_speed": round(current.get("wind_speed_10m", 0)),
            "description": desc,
            "icon": icon,
        },
        "forecast": forecast,
        "error": None,
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    cfg = load_config()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "refresh_interval": cfg["display"]["refresh_interval"],
        "title": cfg["display"].get("title", "Transit Board"),
        "theme": cfg["display"].get("theme", "dark"),
    })


@app.get("/api/data")
async def api_data():
    cfg = load_config()
    async with httpx.AsyncClient(headers={"User-Agent": "HomeTransitBoard/1.0"}) as client:
        tasks = [fetch_departures(client, stop) for stop in cfg["transit"]["stops"]]
        tasks.append(fetch_weather(client, cfg))
        results = await asyncio.gather(*tasks)

    return {
        "stops": list(results[:-1]),
        "weather": results[-1],
        "updated_at": datetime.now(tz=TZ).isoformat(),
    }


@app.get("/api/stops/search")
async def search_stops(q: str):
    """Helper to find MVG global stop IDs by name."""
    async with httpx.AsyncClient(headers={"User-Agent": "HomeTransitBoard/1.0"}) as client:
        try:
            r = await client.get(f"{MVG_BASE}/location", params={"query": q}, timeout=8)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            return {"error": str(e), "results": []}

    return {
        "results": [
            {
                "name": item.get("name"),
                "global_id": item.get("globalId"),
                "products": item.get("products", []),
            }
            for item in data
            if item.get("type") == "STATION"
        ]
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
