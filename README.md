# Minimal Public Status Page (Dynatrace-powered)

This bundle gives you an OpenAI-style, lightweight **public status page** that reads a `health.json` file generated from **Dynatrace Synthetic** metrics.

## What’s inside
- `index.html` — static status UI (no framework).
- `health.json` — example health payload (will be overwritten by the exporter).
- `exporter.py` — Python script that pulls Dynatrace metrics and writes `health.json`.
- `README.md` — this file.

---

## 1) Prerequisites
- **Dynatrace SaaS/Managed** with Synthetic Browser monitors for your site.
- Create a **Dynatrace API token** with scopes: `metrics.read`, `problems.read` (problems optional).
- **Python 3.10+** with `pip`.

---

## 2) Quick Start (Local Demo)
```bash
cd status_page_bundle
# (optional) create venv
python3 -m venv .venv && source .venv/bin/activate
pip install requests

# Set environment (replace with your tenant URL and token)

# Edit exporter.py to put your Synthetic monitor IDs
#   -> search for MONITORS and replace SYNTHETIC_TEST-REPLACE_* with your IDs

# Run exporter (writes ./health.json)
python exporter.py

# Serve the folder to view the page
python -m http.server 8080
# open http://localhost:8080 in your browser
```

---

## 3) Mapping to Your SLOs
By default, status is derived from these thresholds (edit in `exporter.py`):
- Availability SLO: **99.9%** (`AVAIL_SLO = 0.999`)
- P95 full page load: **≤ 3s** (`LOAD_SLO_MS = 3000`)
- P95 TTFB: **≤ 500ms** (`TTFB_SLO_MS = 500`)

Status rules:
- `operational` — availability ≥ SLO **and** p95 load ≤ SLO
- `degraded_performance` — availability ≥ SLO but p95 load > SLO
- `major_outage` — availability < SLO or missing data

---

## 4) Scheduling Updates
### Cron (Linux/macOS)
```bash
crontab -e
# update every minute
* * * * * cd /path/to/status_page_bundle && /usr/bin/env -S bash -lc 'source .venv/bin/activate && python exporter.py'
```

### Windows Task Scheduler
- Action: `python` with arguments `exporter.py`
- Start in: path to the bundle folder
- Trigger: every 1 minute

---

## 5) Deploying Publicly
Any static hosting will work. Options:
- **S3 + CloudFront**: upload all files; ensure `health.json` cache TTL is low (e.g., 60s).
- **Vercel/Netlify**: deploy the folder; set a build hook or CI to run `exporter.py` and commit `health.json`.
- **Nginx**: serve the directory; update `health.json` via cron on the server.

Recommend using a subdomain like **status.yourdomain.com**.

---

## 6) SharePoint Canary (optional)
To detect publishing pipeline stalls:
1. Create a hidden page `/health-canary` with a timestamp in the content.
2. Republish it daily via your pipeline.
3. Add a small function in `exporter.py` to fetch and compare the timestamp, setting `last_publish_age_h` and changing the component status if stale.

---

## 7) Troubleshooting
- **HTTP 401/403 from Dynatrace**: token missing scopes or invalid tenant URL.
- **No values returned**: wrong monitor ID; check Synthetic monitor visibility and timeframe.
- **CORS when hosting elsewhere**: `index.html` reads `health.json` from **same directory**; host both together.

---

## 8) Next Steps
- Add **incidents** by hooking Dynatrace problem notifications (webhook) into a small service that appends to `health.json`.
- Publish **30/90-day uptime bars** by storing daily availability into the `uptime` array.
