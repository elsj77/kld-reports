"""
LeanScaper Data Fetcher — pull live data from all key endpoints.
Returns structured dicts ready to use in SAP↔LeanScaper bridge.
"""
import json, datetime
from ls_auth import get_ls_token, ls_get, ls_internal_get


def get_boards(page, since_days: int = 1) -> list:
    """Get all board items updated since N days ago."""
    since = (datetime.datetime.utcnow() - datetime.timedelta(days=since_days)).strftime("%Y-%m-%dT04:00:00.000Z")
    return ls_get(page, f"/api/boards?since={since}")


def get_employees(page) -> list:
    """Get all active LeanScaper employees."""
    return ls_get(page, "/api/employees")


def get_goals_ytd(page) -> dict:
    """Get all scorecard goals YTD."""
    return ls_get(page, "/api/goal-collections?year=2026&yearFilter=Year+to+Date")


def get_goals_full_year(page) -> dict:
    """Get all scorecard goals for full year."""
    return ls_get(page, "/api/goal-collections?year=2026&yearFilter=Full+Year")


def get_huddles(page) -> dict:
    """Get all scheduled huddles."""
    return ls_get(page, "/api/huddles?")


def get_inventory(page) -> dict:
    """Get all inventory items and levels."""
    items  = ls_get(page, "/api/inventory/items?perPage=10000")
    levels = ls_get(page, "/api/inventory/levels?perPage=10000")
    return {"items": items, "levels": levels}


def get_documents(page) -> list:
    """Get all org documents."""
    return ls_get(page, "/api/documents")


def get_vision_mission(page) -> dict:
    """Get org vision and mission."""
    return ls_get(page, "/api/vision-mission")


def get_notifications(page) -> dict:
    """Get unread notification count."""
    return ls_internal_get(page, "/internal/v1/notifications/count")


def build_full_snapshot(page) -> dict:
    """
    Pull ALL LeanScaper data in one pass.
    Returns a dict with all sections populated.
    """
    print("Pulling LeanScaper full snapshot...", flush=True)
    snap = {}
    snap["boards"]       = get_boards(page)
    snap["employees"]    = get_employees(page)
    snap["goals_ytd"]    = get_goals_ytd(page)
    snap["huddles"]      = get_huddles(page)
    snap["vision"]       = get_vision_mission(page)
    snap["pulled_at"]    = datetime.datetime.utcnow().isoformat()
    print(f"  ✓ Boards: {len(snap['boards'])} | Employees: {len(snap['employees'])} | Huddles: {snap['huddles'].get('pagination',{}).get('total',0)}", flush=True)
    return snap


def summarize_goals(goals_data: dict) -> list:
    """Flatten goal collections into a simple list of {category, name, target, progress}."""
    out = []
    for gc in goals_data.get("goalCollectionsWithGoals", []):
        for g in gc.get("goals", []):
            out.append({
                "category": gc["name"],
                "name": g["name"],
                "target": g.get("targetValue"),
                "progress": g.get("progress", 0),
                "goal_id": g["id"],
                "data_type": g.get("dataType"),
                "allow_manual": g.get("allowManualGoalEntry", False),
            })
    return out


def format_goals_for_context(goals_data: dict) -> str:
    """Format goals as a readable block for Lana context."""
    goals = summarize_goals(goals_data)
    lines = ["LEANSCAPER SCORECARD TARGETS (2026 YTD):"]
    for g in goals:
        t = g["target"]
        if g["data_type"] == "Currency" and t:
            tval = f"${t:,.0f}"
        elif g["data_type"] == "Percentage" and t:
            tval = f"{t}%"
        else:
            tval = str(t) if t else "TBD"
        lines.append(f"  - {g['category']} / {g['name']}: target={tval}, progress={g['progress']}%")
    return "\n".join(lines)
