"""
field_request_router.py — Route field team requests to the right LeanScaper board.

Parses a text message (from WhatsApp/crew) and creates the correct board card.

Board routing logic:
  - Equipment broken/won't start/repair needed → Shop Board
  - Client complaint/damage/callback → Incident Reporting
  - Quote/estimate needed → Customer Board
  - Supply/material order needed → Ops Board (Ordering/Scheduling)
  - General task/action needed → Action Items Board
  - Office/admin/HQ item → HQ Board

Usage:
    python3 field_request_router.py "T-1 Walker mower won't start, blade is bent"
    python3 field_request_router.py "Client at 123 Main St complained about lawn edges"

Returns the created card ID and board/column it went to.
"""

import os, sys, re

env_path = "/app/.agents/.env"
if os.path.exists(env_path):
    for line in open(env_path):
        line = line.strip()
        if line.startswith("export ") and "=" in line:
            k, _, v = line[7:].partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))

sys.path.insert(0, '/app/.agents/skills/leanscaper')
from ls_board_card import create_card

# Routing rules: (pattern list, board, column, priority)
ROUTING_RULES = [
    # Equipment / Shop
    (["mower", "trimmer", "blower", "truck", "trailer", "engine", "blade", "belt",
      "broken", "won't start", "not starting", "repair", "equipment", "machine",
      "tool", "flat tire", "oil", "hydraulic", "fuel leak"],
     "shop", "new", "Medium"),

    # Incidents / Client issues
    (["complaint", "damage", "callback", "unhappy", "angry", "client said", "property damage",
      "hit a rock", "broke a window", "fence", "scratched", "safety incident",
      "near miss", "injury", "hurt", "accident"],
     "incident", "new", "High"),

    # Customer / Sales
    (["quote", "estimate", "new client", "sign up", "interested", "proposal",
      "upsell", "add service", "wants to know price", "how much"],
     "customer", "new", "Medium"),

    # Supplies / Materials
    (["need supplies", "order", "running low", "out of", "need more", "stock",
      "pickup", "parts", "materials", "fertilizer", "chemical", "fuel"],
     "ops", "ordering/scheduling", "Medium"),
]

DEFAULT_ROUTE = ("action", "new", "None")


def route_message(message: str) -> tuple:
    """Returns (board, column, priority) for a given message."""
    msg_lower = message.lower()
    for keywords, board, column, priority in ROUTING_RULES:
        if any(kw in msg_lower for kw in keywords):
            return board, column, priority
    return DEFAULT_ROUTE


def process_field_request(message: str, sender: str = "Field Team") -> dict:
    """
    Parse a field request message and create the appropriate LeanScaper board card.

    Args:
        message: The raw text from the crew member
        sender:  Who sent it (for card title context)

    Returns:
        dict with card id, board, column, and routing info
    """
    board, column, priority = route_message(message)

    # Clean up title
    title = message.strip()
    if len(title) > 100:
        title = title[:97] + "..."

    body = f"**Source:** {sender} via WhatsApp\n\n{message}"

    result = create_card(
        board=board,
        column=column,
        title=title,
        body=body,
        priority=priority
    )

    return {
        "card_id": result.get("id"),
        "board": result.get("board", {}).get("title"),
        "column": result.get("column", {}).get("title"),
        "priority": priority,
        "title": title,
        "routing_keywords_matched": board,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 field_request_router.py 'message text' ['Sender Name']")
        sys.exit(1)

    msg    = sys.argv[1]
    sender = sys.argv[2] if len(sys.argv) > 2 else "Field Team"

    print(f"Routing: {msg[:60]}...")
    result = process_field_request(msg, sender)
    print(f"✅ Card created!")
    print(f"   Board:  {result['board']}")
    print(f"   Column: {result['column']}")
    print(f"   Priority: {result['priority']}")
    print(f"   Card ID: {result['card_id']}")
