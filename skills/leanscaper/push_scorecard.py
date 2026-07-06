"""
LeanScaper Scorecard Push — standalone script.
Reads latest SeasonSnapshot + CrewDayReports from Base44, calculates KPIs,
then pushes them to LeanScaper via Browserbase persistent context.

Usage:
    python3 /app/.agents/skills/leanscaper/push_scorecard.py

Returns JSON: {"ok": true, "pushed": [...], "skipped": [...]}
"""
import os, sys, json, requests, time
sys.path.insert(0, "/app/.agents/skills/leanscaper")

# ── Config ──────────────────────────────────────────────────────────────────
BB_API_KEY   = os.environ.get("BROWSERBASE_API_KEY", "")
BB_PROJECT   = os.environ.get("BROWSERBASE_PROJECT_ID", "")
CONTEXT_ID   = "874f3cbf-e301-4958-b701-f5103f190c45"   # persistent LeanScaper session
BASE44_KEY   = os.environ.get("BASE44_SERVICE_TOKEN", "")
APP_ID       = "69b1e8cc39ff4c79781789de"
LS_FRONT     = "https://ai.leanscaper.com"
YEAR         = 2026
YEAR_FILTER  = "Full Year"

# ── Base44 entity helpers ────────────────────────────────────────────────────
def fetch_entity(entity: str, limit: int = 5, sort: str = "-created_date") -> list:
    url = f"https://base44.app/api/apps/{APP_ID}/entities/{entity}?limit={limit}&sort={sort}"
    r = requests.get(url, headers={"Authorization": f"Bearer {BASE44_KEY}"}, timeout=20)
    r.raise_for_status()
    return r.json() if isinstance(r.json(), list) else []

def get_latest_snapshot() -> dict:
    rows = fetch_entity("SeasonSnapshot", limit=1, sort="-created_date")
    return rows[0] if rows else {}

def get_recent_crew_reports(days: int = 30) -> list:
    return fetch_entity("CrewDayReport", limit=days, sort="-report_date")

# ── KPI calculation ──────────────────────────────────────────────────────────
def build_kpis(snapshot: dict, crew_reports: list) -> dict:
    kpis = {}

    svc_data = snapshot.get("service_data", {})
    if isinstance(svc_data, str):
        try:
            svc_data = json.loads(svc_data)
        except:
            svc_data = {}

    dispatch = svc_data.get("dispatch_board", {}) if isinstance(svc_data, dict) else {}
    wl       = svc_data.get("waiting_list", {})   if isinstance(svc_data, dict) else {}

    # Revenue Sold = dispatch total + waiting list
    dispatch_amt = sum(d.get("amount", 0) for d in dispatch.values() if isinstance(d, dict))
    wl_amt       = sum(d.get("amount", 0) for d in wl.values()       if isinstance(d, dict))
    revenue_sold = dispatch_amt + wl_amt
    if revenue_sold > 0:
        kpis["revenue_sold"] = round(revenue_sold)

    # Revenue Invoiced = completed-weighted portion of dispatch
    invoiced = 0
    for d in dispatch.values():
        if not isinstance(d, dict): continue
        total = d.get("total", 0) or 0
        done  = d.get("Completed", 0) or 0
        amt   = d.get("amount", 0) or 0
        if total > 0 and done > 0 and amt > 0:
            invoiced += (done / total) * amt
    if invoiced > 0:
        kpis["revenue_invoiced"] = round(invoiced)

    # Crew efficiency from reports
    if crew_reports:
        total_mins  = sum(r.get("totals", {}).get("online_mins", 0) or 0 for r in crew_reports)
        total_jobs  = sum(r.get("totals", {}).get("jobs", 0)        or 0 for r in crew_reports)
        total_done  = sum(r.get("totals", {}).get("completed", 0)   or 0 for r in crew_reports)

        if total_jobs > 0 and total_done > 0:
            kpis["crew_efficiency_score_avg"] = round((total_done / total_jobs) * 100, 1)

        hrs = total_mins / 60
        if hrs > 0 and invoiced > 0:
            kpis["revenue_per_hour_actual"] = round(invoiced / hrs, 2)

    print(f"  KPIs calculated: {list(kpis.keys())}", flush=True)
    return kpis

# ── Browserbase session ──────────────────────────────────────────────────────
def create_bb_session() -> tuple:
    """Create a Browserbase session using the persistent LeanScaper context. Returns (session_id, ws_url)."""
    r = requests.post(
        "https://www.browserbase.com/v1/sessions",
        headers={"x-bb-api-key": BB_API_KEY, "Content-Type": "application/json"},
        json={"projectId": BB_PROJECT, "browserSettings": {"context": {"id": CONTEXT_ID, "persist": True}}},
        timeout=20
    )
    r.raise_for_status()
    d = r.json()
    return d["id"], d["connectUrl"]

# ── LeanScaper push via Playwright ───────────────────────────────────────────
def push_to_leanscaper(kpis: dict) -> list:
    from playwright.sync_api import sync_playwright

    results = []
    session_id, ws_url = create_bb_session()
    print(f"  BB session: {session_id}", flush=True)

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(ws_url)
        ctx = browser.contexts[0]
        page = ctx.new_page()

        # Navigate to LeanScaper to establish cookie context
        page.goto(f"{LS_FRONT}/scorecard", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        # Fetch all goal IDs dynamically
        print("  Loading goal IDs from LeanScaper...", flush=True)
        goal_data = page.evaluate("""
            async () => {
                const r = await fetch('/api/goal-collections?year=2026&yearFilter=Full+Year', {credentials:'include'});
                return await r.json();
            }
        """)

        goal_map = {}
        for gc in (goal_data.get("goalCollectionsWithGoals") or []):
            for g in gc.get("goals", []):
                raw = g["name"].lower()
                key = (raw.replace(" ","_").replace("(","").replace(")","")
                           .replace(".","").replace("/","_").replace("-","_"))
                goal_map[key] = {"id": g["id"], "name": g["name"],
                                  "allow_manual": g.get("allowManualGoalEntry", False)}

        print(f"  Found {len(goal_map)} goals in LeanScaper", flush=True)

        for kpi_key, value in kpis.items():
            if kpi_key not in goal_map:
                print(f"  ⚠️  '{kpi_key}' not in goal map — skip", flush=True)
                results.append({"goal": kpi_key, "status": "skipped", "reason": "not_in_goal_map"})
                continue

            g = goal_map[kpi_key]
            body = json.dumps({"goalId": g["id"], "goalName": g["name"],
                               "value": str(value), "year": YEAR, "yearFilter": YEAR_FILTER})
            print(f"  Pushing {g['name']} = {value} ...", flush=True)

            result = page.evaluate(f"""
                async () => {{
                    const r = await fetch('{LS_FRONT}/api/goals/entries', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        credentials: 'include',
                        body: {repr(body)}
                    }});
                    return {{ status: r.status, body: await r.text() }};
                }}
            """)

            status = result.get("status")
            icon = "✅" if status == 200 else "❌"
            print(f"  {icon} {g['name']}: HTTP {status} — {result.get('body','')[:100]}", flush=True)
            results.append({"goal": g["name"], "value": value, "status": status})

        browser.close()

    return results

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("=== LeanScaper Scorecard Push ===", flush=True)

    print("Loading SeasonSnapshot...", flush=True)
    snapshot = get_latest_snapshot()
    snap_date = snapshot.get("generated_at", "unknown")
    print(f"  Snapshot date: {snap_date}", flush=True)

    print("Loading CrewDayReports (last 30)...", flush=True)
    crew_reports = get_recent_crew_reports(30)
    print(f"  {len(crew_reports)} crew reports loaded", flush=True)

    kpis = build_kpis(snapshot, crew_reports)
    if not kpis:
        print("❌ No KPI values calculated — nothing to push", flush=True)
        print(json.dumps({"ok": False, "reason": "no_kpis"}))
        return

    print(f"\nPushing {len(kpis)} KPIs to LeanScaper...", flush=True)
    results = push_to_leanscaper(kpis)

    pushed  = [r for r in results if r.get("status") == 200]
    skipped = [r for r in results if r.get("status") != 200]

    print(f"\n✅ Done — {len(pushed)} pushed, {len(skipped)} skipped/failed", flush=True)
    print(json.dumps({"ok": True, "pushed": pushed, "skipped": skipped}, indent=2))

if __name__ == "__main__":
    main()
