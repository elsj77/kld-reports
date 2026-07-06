"""
ls_board_card.py — Create cards on LeanScaper boards via the internal API.

No browser required. Uses LEANSCAPER_JWT from .agents/.env.

Usage (module):
    from ls_board_card import create_card, BOARDS, get_column_id
    card = create_card(
        board="ops",
        column="New",
        title="Fix irrigation head at 123 Main St",
        body="Client called at 2pm. Job #4521.",
        priority="High"
    )

Usage (CLI):
    python3 ls_board_card.py ops "New" "Fix irrigation head" "Details here" High
"""

import os, sys, json, urllib.request

# Load env
env_path = "/app/.agents/.env"
if os.path.exists(env_path):
    for line in open(env_path):
        line = line.strip()
        if line.startswith("export ") and "=" in line:
            k, _, v = line[7:].partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))

LS_API = "https://api.leanscaper.com"

# Board + column registry (confirmed 2026-06-06)
BOARDS = {
    "ops": {
        "id": "ee67d4a9-ff1b-4564-8739-05ee80da97ab",
        "name": "Ops Board",
        "columns": {
            "new":                 "e4bb1cb2-d6ae-4a21-b602-01ee6348b187",
            "ordering/scheduling": "1e9bf93e-4337-4f87-bfb5-42319463426a",
            "delivering":          "cc3794d4-fabf-48d3-b15b-b37d38cc5013",
            "done":                "43fd0476-7eb8-432e-abc6-b6c7bc43db61",
            "cancelled":           "10b05c1d-0a47-4097-96aa-f01f20117e74",
        }
    },
    "incident": {
        "id": "4d1315d0-849f-4afe-9465-af53f88e2cff",
        "name": "Incident Reporting",
        "columns": {
            "new":             "e8a791e0-434c-472a-ac2f-05798c883acf",  # TODO: confirm IDs
            "reviewing":       "89a70f13-adfc-4838-be94-acad508db227",
            "in progress":     "68e01aa2-798d-41cb-aa2f-d7ba6ff7721e",
            "waiting":         "ac5d6952-a99e-4ffd-b97b-532ad8040a55",
            "verify complete": "8f823ccb-b827-4c16-bd04-b155c18c2ae3",
            "closed":          "ccfff40c-7a3f-440a-9210-4ce4d64c0d17",
            "dismissed":       "50a35871-f7eb-4002-99b0-e8ddff819bbb",
        }
    },
    "action": {
        "id": "1d4dfdd9-56be-4103-89cf-97fdfec8090b",
        "name": "Action Items Board",
        "columns": {
            "new":         "41a6a63c-1f2f-493b-b256-5f69a9c77ba0",
            "planning":    "291cfc44-bfc6-4c75-af40-d4c31ca2e7d1",
            "in progress": "6592de0a-4b0d-46e7-886f-7482a19be200",
            "done":        "c9857c81-4aea-4dab-becd-ac39a4d03a22",
            "cancelled":   "afc5c05a-879a-4723-b993-047545904a5a",
        }
    },
    "customer": {
        "id": "6e902d2c-24e2-449f-9558-0a0222bee142",
        "name": "Customer Board",
        "columns": {
            "new":              "2e7a0aa4-ecd7-4d3d-bba4-e600b67f262c",
            "scoping":          "f746acd2-e938-4877-8844-e618983c2108",
            "sent/scheduled":   "f7ad08d0-723a-4e41-a8f9-bd63fb52e164",
            "signed/sold/done": "ca58d61f-06be-49c7-a9da-20b1c2ac81b3",
            "declined/void":    "59fad991-d0ae-48ea-8ddb-c2ad25eef1d7",
        }
    },
    "shop": {
        "id": "9adac93e-a60b-40a4-bfe5-2931f0855e32",
        "name": "Shop Board",
        "columns": {
            "new":              "52eabde4-048a-4f7a-8fe8-115b3067407f",
            "diagnosing":       "ed711c05-a93e-4e44-831a-3f291678f776",
            "waiting on parts": "e4919ebe-dd85-444b-9d9b-e252e9301c35",
            "fixing":           "83dff05b-6dd7-4ead-b117-119d15ef085a",
            "done":             "c292fb60-8fd2-49dd-b0ba-e8869f6bb35d",
            "scrapped":         "669067db-9a88-40d2-9736-a94eaea7f13f",
        }
    },
    "hq": {
        "id": "dd79fbff-aacf-4cbe-98f4-e16ef9625748",
        "name": "HQ Board",
        "columns": {
            "new":                      "daf8130a-10c4-4da8-9ca4-bbe4d3204295",
            "reviewing":                "456fe99d-fc9a-4ec1-a7b0-964e7e1c2bbc",
            "in progress/approved":     "c6344723-398b-4ccf-80bd-db5a295980d8",
            "done/recorded":            "bb8ce48f-8323-4f9e-a7d8-3750c198736a",
            "denied/invalid":           "9109b618-93a9-4a58-82f7-31e9cc9c476e",
        }
    },
}


def get_column_id(board_key: str, column_name: str) -> str:
    """Fuzzy match column name to ID. Raises if not found."""
    board = BOARDS.get(board_key.lower())
    if not board:
        raise ValueError(f"Unknown board: {board_key}. Options: {list(BOARDS.keys())}")
    col_name_lower = column_name.lower()
    cols = board["columns"]
    # Exact match first
    if col_name_lower in cols:
        return cols[col_name_lower]
    # Partial match
    for key, col_id in cols.items():
        if col_name_lower in key or key in col_name_lower:
            return col_id
    raise ValueError(f"Column '{column_name}' not found in {board['name']}. Options: {list(cols.keys())}")


def create_card(
    board: str,
    column: str,
    title: str,
    body: str = "",
    priority: str = "None",
    due_date: str = None,
    labels: list = None,
    token: str = None
) -> dict:
    """
    Create a card on a LeanScaper board.

    Args:
        board:    Board key (ops, incident, action, customer, shop, hq)
        column:   Column name (fuzzy matched)
        title:    Card title (required)
        body:     Card description
        priority: None | Low | Medium | High
        due_date: ISO date string e.g. "2026-06-10"
        labels:   List of label strings
        token:    JWT override (uses LEANSCAPER_JWT env if not provided)

    Returns:
        dict: Full card response from API
    """
    if token is None:
        token = os.environ.get("LEANSCAPER_JWT", "")
    if not token:
        raise RuntimeError("LEANSCAPER_JWT not set. Run refresh_lana_token.py or re-auth.")

    board_data = BOARDS.get(board.lower())
    if not board_data:
        raise ValueError(f"Unknown board: {board}")

    col_id = get_column_id(board, column)
    board_id = board_data["id"]

    payload = {
        "title": title,
        "boardColumnId": col_id,
        "body": body,
        "priority": priority,
        "labels": labels or [],
    }
    if due_date:
        payload["dueDate"] = due_date

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    req = urllib.request.Request(
        f"{LS_API}/internal/v1/boards/{board_id}/cards",
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def list_boards() -> dict:
    """Return the BOARDS registry."""
    return {k: {"name": v["name"], "id": v["id"], "columns": list(v["columns"].keys())}
            for k, v in BOARDS.items()}


# ─── CLI ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python3 ls_board_card.py <board> <column> <title> [body] [priority]")
        print(f"Boards: {list(BOARDS.keys())}")
        sys.exit(1)

    board   = sys.argv[1]
    column  = sys.argv[2]
    title   = sys.argv[3]
    body    = sys.argv[4] if len(sys.argv) > 4 else ""
    priority= sys.argv[5] if len(sys.argv) > 5 else "None"

    print(f"Creating card on {board}/{column}: {title}")
    result = create_card(board, column, title, body, priority)
    if "id" in result:
        print(f"✅ Created: {result['id']} | Board: {result['board']['title']} | Col: {result['column']['title']}")
    else:
        print(f"❌ Error: {result}")
