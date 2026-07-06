"""
LeanScaper Board Card Creator — auto-create cards from SAP events.

Board IDs (from /api/boards, confirmed live):
  Continuous Improvement: 156d67c9-3d9a-4272-9cae-b99e5c4df3d0
  Action Items:           1d4dfdd9-56be-4103-89cf-97fdfec8090b
  Customer:               (need to fetch — 3rd board)
  Shop:                   (need to fetch — 4th board)
  HQ:                     (need to fetch — 5th board)
  Ops:                    (need to fetch — 6th board)

Card creation endpoint: TBD — needs CDP sniff of board UI click.
Candidate: POST /api/boards/{boardId}/cards
"""
import json, datetime

LS_FRONT = "https://ai.leanscaper.com"
LS_API_BASE = "https://api.leanscaper.com"

# Board IDs — confirmed from CDP capture
BOARD_IDS = {
    "continuous_improvement": "156d67c9-3d9a-4272-9cae-b99e5c4df3d0",
    "action_items":           "1d4dfdd9-56be-4103-89cf-97fdfec8090b",
    # These need to be fetched — fetched dynamically via get_board_ids()
    "customer": None,
    "shop":     None,
    "hq":       None,
    "ops":      None,
}


def get_board_ids(page) -> dict:
    """Fetch all board IDs from LeanScaper."""
    import datetime
    since = (datetime.datetime.utcnow() - datetime.timedelta(days=30)).strftime("%Y-%m-%dT04:00:00.000Z")
    boards = page.evaluate(f"""
        async () => {{
            const r = await fetch('/api/boards?since={since}', {{credentials:'include'}});
            return await r.json();
        }}
    """)
    
    id_map = {}
    for b in boards:
        title = b.get("title","").lower()
        bid = b.get("id")
        if "customer" in title:    id_map["customer"] = bid
        elif "shop" in title:      id_map["shop"] = bid
        elif "hq" in title:        id_map["hq"] = bid
        elif "ops" in title:       id_map["ops"] = bid
        elif "action" in title:    id_map["action_items"] = bid
        elif "improvement" in title: id_map["continuous_improvement"] = bid
        id_map[b.get("title","").lower().replace(" ","_")] = bid
    
    return id_map


def try_create_card(page, token: str, board_id: str, title: str, description: str = "", priority: str = "medium") -> dict:
    """
    Try multiple endpoint patterns to create a board card.
    """
    today = datetime.date.today().isoformat()
    
    card_body = {
        "title": title,
        "description": description,
        "boardId": board_id,
        "priority": priority,
        "dueDate": today,
    }
    body_str = json.dumps(card_body)
    
    candidates = [
        f"{LS_FRONT}/api/boards/{board_id}/cards",
        f"{LS_FRONT}/api/boards/{board_id}/items",
        f"{LS_API_BASE}/internal/v1/boards/{board_id}/cards",
        f"{LS_FRONT}/api/cards",
    ]
    
    for url in candidates:
        result = page.evaluate(f"""
            async (token) => {{
                const r = await fetch('{url}', {{
                    method: 'POST',
                    headers: {{
                        'Authorization': 'Bearer ' + token,
                        'Content-Type': 'application/json'
                    }},
                    credentials: 'include',
                    body: {repr(body_str)}
                }});
                return {{ status: r.status, url: '{url}', body: (await r.text()).substring(0, 300) }};
            }}
        """, token)
        print(f"  POST {url.replace(LS_FRONT,'').replace(LS_API_BASE,'[api]')[:60]} → {result.get('status')}", flush=True)
        if result.get("status") in (200, 201):
            print(f"  ✅ Card created!", flush=True)
            return result
    
    return {"success": False, "tried": len(candidates)}


# ── SAP Event → Board Card Rules ─────────────────────────────────────────────

def sap_event_to_board_card(event_type: str, event_data: dict) -> dict | None:
    """
    Map SAP events to LeanScaper board cards.
    Returns {board: str, title: str, description: str, priority: str} or None.
    """
    rules = {
        "equipment_issue":     ("shop", "high"),
        "customer_complaint":  ("customer", "high"),
        "incomplete_route":    ("ops", "medium"),
        "fw2_route_gap":       ("ops", "medium"),
        "invoice_overdue":     ("action_items", "high"),
        "new_hire_needed":     ("hq", "medium"),
        "material_low":        ("shop", "medium"),
    }
    
    if event_type not in rules:
        return None
    
    board_key, priority = rules[event_type]
    
    title_templates = {
        "equipment_issue":     "🔧 Equipment Issue: {detail}",
        "customer_complaint":  "⚠️ Customer Issue: {detail}",
        "incomplete_route":    "📍 Incomplete Route: {detail}",
        "fw2_route_gap":       "🌿 FW2 Route Gap: {detail}",
        "invoice_overdue":     "💰 Invoice Overdue: {detail}",
        "new_hire_needed":     "👤 Hire Needed: {detail}",
        "material_low":        "📦 Low Stock: {detail}",
    }
    
    detail = event_data.get("detail", event_data.get("name", "Unknown"))
    title = title_templates.get(event_type, f"{event_type}: {detail}").format(detail=detail)
    
    return {
        "board": board_key,
        "title": title,
        "description": event_data.get("description", ""),
        "priority": priority,
    }


def check_sap_for_board_events(sap_snapshot: dict) -> list:
    """
    Scan the SAP season snapshot for conditions that should generate board cards.
    Returns list of {event_type, event_data} dicts.
    """
    events = []
    
    svc = {}
    raw = sap_snapshot.get("service_data", {})
    if isinstance(raw, dict):
        svc = raw.get("dispatch_board", raw)
    
    # Check mowing velocity — if pending > 800 it's a risk worth flagging on Ops board
    mowin = svc.get("MOWIN", {})
    elkmow = svc.get("ELKMOW", {})
    total_mow_pending = mowin.get("Pending", 0) + elkmow.get("Pending", 0)
    if total_mow_pending > 1000:
        events.append({
            "event_type": "incomplete_route",
            "event_data": {
                "detail": f"Mowing backlog: {total_mow_pending:,} jobs pending",
                "description": f"MOWIN: {mowin.get('Pending',0)} pending, ELKMOW: {elkmow.get('Pending',0)} pending. Target: 400+ completions/week."
            }
        })
    
    # Check FW2 route readiness
    wl = {}
    if isinstance(raw, dict):
        wl = raw.get("waiting_list", {})
    fw2_count = wl.get("FW2", {}).get("total", 0)
    if fw2_count > 100:
        fw2_amt = wl.get("FW2", {}).get("amount", 0)
        events.append({
            "event_type": "fw2_route_gap",
            "event_data": {
                "detail": f"{fw2_count} jobs / ${fw2_amt:,.0f} waiting",
                "description": "FW2 confirmed but not yet scheduled. Needs route buckets locked."
            }
        })
    
    return events
