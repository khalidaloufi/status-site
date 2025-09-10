#!/usr/bin/env python3
import os, sys, json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import requests
from collections import defaultdict

# SSL verification controls (for Managed clusters with private CA)
CA_BUNDLE = os.environ.get("CA_BUNDLE", "").strip()  # path to a PEM file (custom CA/chain)
VERIFY_SSL = os.environ.get("VERIFY_SSL", "true").strip().lower() not in {"0", "false", "no"}

def _verify_param():
    # If a CA bundle path is provided, prefer it; else use boolean VERIFY_SSL
    return CA_BUNDLE if CA_BUNDLE else VERIFY_SSL

AVAIL_SLO = 0.999   # 99.9%
LOAD_SLO_MS = 3000  # 3s P95 full-page load
TTFB_SLO_MS = 500

MONITORS = [
    #{"name": "Public Website (KSA)", "monitor_id": "HTTP_CHECK-EB933FDD43BF481C"},
    {"name": "Public Website (KSA)", "monitor_id": "HTTP_CHECK-18ACCCACE63A1420", "type": "HTTP"},

]


GLOBAL_COMPONENT_NAME = "Public Website (Global)"
PUBLISHING_COMPONENT = {"name": "Publishing Pipeline"}  # fill last_publish_age_h if you add a canary

def dt_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Api-Token {token}", "Accept": "application/json"}

def query_metric(base: str, token: str, metric_selector: str, time_from: str = "now-15m", resolution: str = "Inf") -> Optional[Dict[str, Any]]:
    url = f"{base}/api/v2/metrics/query"
    params = {
        "metricSelector": metric_selector,
        "from": time_from,
        "resolution": resolution,
    }
    try:
        r = requests.get(
            url,
            headers=dt_headers(token),
            params=params,
            timeout=20,
            verify=_verify_param(),
        )
    except requests.exceptions.SSLError as e:
        print("[ssl] SSL verification failed while calling:", url, file=sys.stderr)
        print("[ssl] Hint: set CA_BUNDLE to a PEM file with your Dynatrace Managed root/issuer certs, e.g.:", file=sys.stderr)
        print("[ssl]   export CA_BUNDLE=/path/to/noc_chain.pem", file=sys.stderr)
        print("[ssl] For a temporary test only, you can disable verification with:", file=sys.stderr)
        print("[ssl]   export VERIFY_SSL=false", file=sys.stderr)
        raise
    if r.status_code != 200:
        print(f"[warn] {metric_selector} -> HTTP {r.status_code}: {r.text[:200]}", file=sys.stderr)
        return None
    return r.json()

def _load_previous(out_path: str) -> Dict[str, Any]:
    try:
        with open(out_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _map_components_by_name(components: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {c.get("name"): c for c in (components or [])}

def last_value(series_json: Dict[str, Any]) -> Optional[float]:
    try:
        return float(series_json["result"][0]["data"][0]["values"][0])
    except Exception:
        return None

def component_status(availability: Optional[float], p95_load_ms: Optional[float]) -> str:
    if availability is None or availability < AVAIL_SLO:
        return "major_outage"
    # If no p95 metric is provided (e.g., HTTP monitor without browser timings), consider it operational
    return "operational" if (p95_load_ms is None or p95_load_ms <= LOAD_SLO_MS) else "degraded_performance"

# --- Minute-bucket helpers for stable timestamps ---

def round_now_to_minute_utc() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(second=0, microsecond=0)


def query_metric_fixed_minute(base: str, token: str, metric_selector: str, end_utc: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """Query a single 1-minute bucket ending at end_utc (rounded to minute)."""
    if end_utc is None:
        end_utc = round_now_to_minute_utc()
    start_utc = end_utc - timedelta(minutes=1)

    url = f"{base}/api/v2/metrics/query"
    params = {
        "metricSelector": metric_selector,
        "from": int(start_utc.timestamp() * 1000),  # ms epoch
        "to": int(end_utc.timestamp() * 1000),      # ms epoch
        "resolution": "1m",
    }
    try:
        r = requests.get(
            url,
            headers=dt_headers(token),
            params=params,
            timeout=20,
            verify=_verify_param(),
        )
    except requests.exceptions.SSLError:
        print("[ssl] SSL verification failed while calling:", url, file=sys.stderr)
        print("[ssl] Hint: provide CA_BUNDLE or set VERIFY_SSL=false for testing.", file=sys.stderr)
        raise
    if r.status_code != 200:
        print(f"[warn] {metric_selector} -> HTTP {r.status_code}: {r.text[:200]}", file=sys.stderr)
        return None
    return r.json()


def extract_single_value(series_json: Optional[Dict[str, Any]]) -> Optional[float]:
    """Extract a single numeric value from a v2 metrics response (uses the last value)."""
    try:
        vals = series_json["result"][0]["data"][0]["values"]
        if not vals:
            return None
        return float(vals[-1])
    except Exception:
        return None


def append_minute_sample(minute_samples: Dict[str, List[Dict[str, Any]]], component_name: str, bucket_end: datetime, availability: Optional[float]) -> Dict[str, List[Dict[str, Any]]]:
    series = minute_samples.get(component_name) or []
    iso = bucket_end.isoformat().replace("+00:00", "Z")
    # avoid duplicate if this minute already exists as the last point
    if not series or series[-1].get("t") != iso:
        series.append({"t": iso, "availability": round((availability or 0.0), 6)})
        # keep at most last 7 days of 1-minute samples (10080 points)
        series = series[-10080:]
    minute_samples[component_name] = series
    return minute_samples

def main():
    base = os.environ.get("DYNATRACE_URL", "").rstrip("/")
    token = os.environ.get("DYNATRACE_TOKEN", "")
    out_path = os.environ.get("OUTPUT_PATH", "health.json")

    if not base or not token:
        print("ERROR: Set DYNATRACE_URL and DYNATRACE_TOKEN environment variables.", file=sys.stderr)
        sys.exit(1)

    prev = _load_previous(out_path)
    prev_components_map = _map_components_by_name(prev.get("components", []))
    minute_samples: Dict[str, List[Dict[str, Any]]] = prev.get("minute_samples", {}) or {}

    # Use a fixed, rounded minute for stable timestamps in this run
    bucket_end = round_now_to_minute_utc()

    components: List[Dict[str, Any]] = []

    for m in MONITORS:
        monitor_id = m["monitor_id"]
        name = m["name"]

        # 15m availability for current status
        avail_15m = query_metric(
            base,
            token,
            f'builtin:synthetic.http.availability.location.total:filter(eq(dt.entity.http_check,"{monitor_id}")):splitBy():avg',
            time_from="now-15m",
            resolution="Inf",
        )
        availability_pct_15m = last_value(avail_15m)
        availability_15m = (availability_pct_15m / 100.0) if availability_pct_15m is not None else None

        # Exact 1-minute bucket for stable time series (per-minute sample)
        avail_1m_json = query_metric_fixed_minute(
            base,
            token,
            f'builtin:synthetic.http.availability.location.total:filter(eq(dt.entity.http_check,"{monitor_id}")):splitBy():avg',
            end_utc=bucket_end,
        )
        availability_pct_1m = extract_single_value(avail_1m_json)
        availability_1m = (availability_pct_1m / 100.0) if availability_pct_1m is not None else None
        minute_samples = append_minute_sample(minute_samples, name, bucket_end, availability_1m)

        # HTTP monitors don’t expose browser timings; keep None unless you add Browser monitors
        p95_load_ms = None
        ttfb_ms = None

        status = component_status(availability_15m, p95_load_ms)

        components.append({
            "name": name,
            "status": status,
            "p95_load_ms": p95_load_ms,
            "ttfb_ms": ttfb_ms,
            "availability": availability_15m,
        })

    # Incident management (open on transition to non-operational, close on recovery)
    incidents: List[Dict[str, Any]] = prev.get("incidents", []) or []
    now_iso = datetime.now(timezone.utc).isoformat()

    for c in components:
        name = c["name"]
        cur_status = c["status"]
        prev_status = (prev_components_map.get(name) or {}).get("status", "operational")

        # Open new incident
        if prev_status == "operational" and cur_status in {"degraded_performance", "major_outage"}:
            incidents.insert(0, {
                "title": f"{name} {('degraded' if cur_status=='degraded_performance' else 'outage')}",
                "description": f"Status changed to {cur_status.replace('_',' ')} based on 15m availability/SLO.",
                "startTime": now_iso,
                "endTime": None,
            })
        # Close latest matching open incident if recovered
        if prev_status in {"degraded_performance", "major_outage"} and cur_status == "operational":
            for inc in incidents:
                if inc.get("endTime") is None and name.split()[0] in inc.get("title", ""):
                    inc["endTime"] = now_iso
                    break

    # Global status
    if any(c["status"] == "major_outage" for c in components):
        global_status = "major_outage"
    elif any(c["status"] == "degraded_performance" for c in components):
        global_status = "degraded_performance"
    else:
        global_status = "operational"

    components.insert(0, {"name": GLOBAL_COMPONENT_NAME, "status": global_status})
    components.append({**PUBLISHING_COMPONENT, "status": "operational", "last_publish_age_h": 3})

    # Build per-component daily series and overall daily series for 90-day grid
    daily_by_comp = rollup_daily_per_component(minute_samples)
    overall_daily = merge_overall_daily(daily_by_comp)

    health = {
        "updatedAt": bucket_end.isoformat(),
        "components": components,
        "incidents": incidents,
        "uptime": overall_daily,          # overall daily series for the top row
        "daily_uptime": daily_by_comp,    # per-component daily series
        "minute_samples": minute_samples, # raw minute data (optional)
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(health, f, ensure_ascii=False, indent=2)

    print(f"Wrote {out_path}")

def rollup_daily_per_component(minute_samples: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    minute_samples = { "Component A": [{"t":"2025-09-08T12:34:00Z","availability":1.0}, ...], ... }
    returns { "Component A": [{"date":"YYYY-MM-DD","pct":0.99923}, ...], ... }
    """
    daily_by_comp: Dict[str, List[Dict[str, Any]]] = {}
    for comp, series in (minute_samples or {}).items():
        by_day: Dict[str, List[float]] = defaultdict(list)
        for pt in series:
            t = str(pt.get("t", ""))[:10]  # YYYY-MM-DD
            av = pt.get("availability")
            if isinstance(av, (int, float)):
                by_day[t].append(float(av))
        # daily mean
        days = []
        for d in sorted(by_day.keys()):
            vals = by_day[d]
            if vals:
                days.append({"date": d, "pct": round(sum(vals) / len(vals), 6)})
        # keep last 120 days
        daily_by_comp[comp] = days[-120:]
    return daily_by_comp

def merge_overall_daily(daily_by_comp: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Merge all components' daily series into one overall daily uptime = mean across components for that day.
    """
    bucket: Dict[str, List[float]] = defaultdict(list)
    for comp, rows in (daily_by_comp or {}).items():
        for r in rows:
            d = r.get("date")
            p = r.get("pct")
            if d and isinstance(p, (int, float)):
                bucket[d].append(float(p))
    out = []
    for d in sorted(bucket.keys()):
        vals = bucket[d]
        if vals:
            out.append({"date": d, "pct": round(sum(vals) / len(vals), 6)})
    return out[-120:]


if __name__ == "__main__":
    main()
