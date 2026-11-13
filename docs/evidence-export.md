# Evidence Export

All exports are generated from stored records. Paths assume the default local setup: the UI at `http://127.0.0.1:5173` proxies `/api` to the backend at `127.0.0.1:8000`.

| Evidence | How to get it |
|---|---|
| **Acceptance report (HTML, printable)** | UI: Acceptance → intake → run → **Report** → *Print / PDF*. Direct: `GET /api/acceptance/runs/{id}/report.html`, then print to PDF from the browser. |
| **Acceptance report (JSON)** | `GET /api/acceptance/runs/{id}/report.json` (served as a download). Contains the snapshots, every check result with evidence, the source and timestamps. |
| **Run comparison** | `GET /api/acceptance/compare?a={runId}&b={runId}` |
| **Incident post-incident summary** | UI: Incident → **Summary** → *Markdown*. Direct: `GET /api/incidents/{id}/summary.md` (or `/summary` for JSON). |
| **Jira payload** | `GET /api/incidents/{id}/export/jira`. A JSON body for `POST /rest/api/2/issue`. RackOps Lab does not call Jira; replace `<PROJECT_KEY>` and submit it yourself. |
| **Incident detail and evidence** | `GET /api/incidents/{id}` (events, hypotheses, repairs, verifications, evidence with provenance). |
| **Metric series** | `GET /api/incidents/{id}/metrics-series` |
| **Recovery measurements** | `GET /api/incidents/metrics` (per source; definitions included) |
| **Audit log** | `GET /api/audit?limit=500&offset=0[&entity_type=…&entity_id=…&origin=…]`. UI: Settings → Audit log, or a device or asset → Audit tab. |
| **Case study** | UI: `/projects/{slug}` → *Print case study*. Controls are hidden in print, and empty candidate fields print as "[Not yet written]". |
| **QR labels** | UI: Racks & cabling → **Labels** → *Print labels*. Each QR code encodes the local record route. |
| **API schema** | `GET /api/openapi.json`. Interactive docs at `/api/docs`. |
| **Raw database** | `backend/data/rackops.db` (SQLite, WAL). Copy it while the backend is stopped, or use `sqlite3 rackops.db ".backup out.db"`. |

Before sharing an export, confirm its source label. `SIMULATED` exports describe drills in a modeled lab, not events on real equipment.
