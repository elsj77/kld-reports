"""
LeanScaper Scorecard Feed — push real SAP numbers into LeanScaper goals.

CONFIRMED ENDPOINT (sniffed via CDP 2026-05-22):
  POST /api/goals/entries
  Body: {"goalId":"...","goalName":"...","value":"750000","year":2026,"yearFilter":"Full Year"}
  Auth: session cookies (credentials: 'include') — NO Bearer token needed
"""
import json

LS_FRONT = "https://ai.leanscaper.com"

# Goal IDs confirmed from /api/goal-collections (2026)
GOAL_IDS = {
    "revenue_sold":     {"id": "7aad4ad8-b64e-49f5-a772-51648fe4b890", "name": "Revenue (Sold)",            "type": "Currency"},
    "revenue_invoiced": {"id": "4db21bf1-69d5-407e-9767-c4870b63572e", "name": "Revenue (Invoiced)",        "type": "Currency"},
    # Additional IDs to be fetched dynamically via load_goal_ids()
}

def load_goal_ids(page) -> dict:
    """Fetch all goal IDs from LeanScaper and return a flat mapping keyed by name."""
    data = page.evaluate("""
        async () => {
            const r = await fetch('/api/goal-collections?year=2026&yearFilter=Full+Year', {credentials:'include'});
            return await r.json();
        }
    """)
    id_map = {}
    for gc in data.get("goalCollectionsWithGoals", []):
        for g in gc.get("goals", []):
            key = g["name"].lower().replace(" ","_").replace("(","").replace(")","").replace(".","").replace("/","_").replace("-","_")
            id_map[key] = {
                "id":           g["id"],
                "name":         g["name"],
                "type":         g.get("dataType",""),
                "target":       g.get("targetValue"),
                "progress":     g.get("progress", 0),
                "collection":   gc["name"],
                "allow_manual": g.get("allowManualGoalEntry", False),
            }
    return id_map


def push_goal_value(page, goal_id: str, goal_name: str, value: float, year: int = 2026, year_filter: str = "Full Year") -> dict:
    """
    Push a value to a LeanScaper scorecard goal.
    CONFIRMED endpoint: POST /api/goals/entries
    """
    body = {"goalId": goal_id, "goalName": goal_name, "value": str(int(value)), "year": year, "yearFilter": year_filter}
    body_str = json.dumps(body)
    result = page.evaluate(f"""
        async () => {{
            const r = await fetch('{LS_FRONT}/api/goals/entries', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                credentials: 'include',
                body: {repr(body_str)}
            }});
            return {{ status: r.status, body: await r.text() }};
        }}
    """)
    return result


def push_all_sap_values(page, sap_values: dict, goal_map: dict) -> list:
    """
    Push a dict of {{goal_key: value}} to LeanScaper.
    sap_values: e.g. {"revenue_sold": 750000, "revenue_invoiced": 680000}
    goal_map: from load_goal_ids()
    Returns list of results.
    """
    results = []
    for key, value in sap_values.items():
        if key not in goal_map:
            print(f"  ⚠️  Goal key '{key}' not found in goal map — skipping", flush=True)
            continue
        g = goal_map[key]
        print(f"  Pushing {g['name']} = {value} ...", flush=True)
        result = push_goal_value(page, g["id"], g["name"], value)
        status = result.get("status")
        icon = "✅" if status == 200 else "❌"
        print(f"  {icon} {g['name']}: HTTP {status}", flush=True)
        results.append({"goal": g["name"], "value": value, "status": status, "response": result.get("body","")[:200]})
    return results


def build_sap_goal_values(season_snapshot: dict, crew_reports: list) -> dict:
    """
    Calculate scorecard values from SAP data.
    Returns dict of {goal_key: numeric_value} ready to push.
    """
    values = {}

    svc_data = season_snapshot.get("service_data", {})
    if not isinstance(svc_data, dict):
        return values

    dispatch = svc_data.get("dispatch_board", {})
    wl = svc_data.get("waiting_list", {})

    # Revenue Sold — all confirmed jobs (dispatch completed + waiting list confirmed)
    total_dispatch_value = 0
    total_completed_value = 0
    for svc_name, d in dispatch.items():
        if not isinstance(d, dict): continue
        amt = d.get("amount", 0)
        total_val = d.get("total", 0)
        completed = d.get("Completed", 0)
        total_dispatch_value += amt
        if total_val > 0 and completed > 0 and amt > 0:
            total_completed_value += (completed / total_val) * amt

    wl_total = sum(d.get("amount", 0) for d in wl.values() if isinstance(d, dict))
    values["revenue_sold"] = round(total_dispatch_value + wl_total)
    values["revenue_invoiced"] = round(total_completed_value)

    # Labor cost from crew reports
    if crew_reports:
        total_hours = sum(r.get("totals", {}).get("online_mins", 0) / 60 for r in crew_reports)
        total_cost = sum(r.get("totals", {}).get("cost", 0) for r in crew_reports)
        total_jobs = sum(r.get("totals", {}).get("jobs", 0) for r in crew_reports)
        total_completed = sum(r.get("totals", {}).get("completed", 0) for r in crew_reports)

        if total_hours > 0 and total_completed_value > 0:
            values["revenue_per_hour_actual"] = round(total_completed_value / total_hours, 2)

        if total_jobs > 0 and total_completed > 0:
            values["job_completion_rate"] = round((total_completed / total_jobs) * 100, 1)

    return values
