#!/usr/bin/env python3
"""
query_agent.py — Query any LeanScaper agent with context injection.

Usage:
    python3 query_agent.py <agent_key> "Your question here"
    python3 query_agent.py --list                    # show all available agents
    python3 query_agent.py --test                    # test all agents are reachable

Available agent keys:
    leanscaperos, sop-agent, estimate-analyzer, icp-agent, cmo-agent,
    lean-leadership-development, job-description-agent, one-year-operations-plan,
    one-year-people-plan, one-year-finance-plan, one-year-customer-plan,
    strategic-planning-agent, enterprise-value-gap-analyzer, vision-creation,
    morning-rollout, lean-operations-certification, business-assessment,
    revenue-control-certification

Auth: email/password (LEANSCAPER_EMAIL/LEANSCAPER_PASSWORD) → JWT (LEANSCAPER_JWT)
      Org routing via X-Organization-Id header (LEANSCAPER_ORG_UUID)
"""

import os, sys, json, requests, time

BASE = "https://api.leanscaper.com"

def get_headers():
    jwt = os.environ.get("LEANSCAPER_JWT", "")
    org = os.environ.get("LEANSCAPER_ORG_UUID", "09c7c652-a7c7-492e-a65b-759db4ddba45")
    if not jwt:
        # Try loading from .env file
        env_path = "/app/.agents/.env"
        if os.path.exists(env_path):
            for line in open(env_path):
                line = line.strip()
                if line.startswith("export ") and "=" in line:
                    k, _, v = line[7:].partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))
        jwt = os.environ.get("LEANSCAPER_JWT", "")
    return {
        "Authorization": f"Bearer {jwt}",
        "X-Organization-Id": org,
        "Content-Type": "application/json"
    }

def list_agents():
    hdrs = get_headers()
    r = requests.get(f"{BASE}/internal/v1/agents", headers=hdrs, timeout=15)
    agents = r.json().get("agents", [])
    print(f"{'Key':<40} {'Category':<15} Name")
    print("-" * 90)
    for a in sorted(agents, key=lambda x: (x.get("category") or x.get("type",""), x["id"])):
        cat = a.get("category") or a.get("type","?")
        print(f"  {a['id']:<38} {cat:<15} {a['name']}")

def parse_sse(text):
    """Extract text from SSE stream. Uses 'delta' field for text-delta events."""
    parts = []
    for line in text.split("\n"):
        if line.startswith("data: "):
            try:
                d = json.loads(line[6:])
                if d.get("type") == "text-delta":
                    parts.append(d.get("delta", ""))
            except:
                pass
    return "".join(parts)

def query_agent(agent_key, question, context="", conversation_id=None, verbose=False):
    """
    Query a LeanScaper agent.
    
    Returns (conversation_id, response_text)
    Pass conversation_id to continue an existing conversation.
    """
    hdrs = get_headers()
    
    # Create or reuse conversation
    if not conversation_id:
        r = requests.post(f"{BASE}/internal/v1/conversations",
            headers=hdrs, json={"agentId": agent_key}, timeout=15)
        if r.status_code != 200:
            raise Exception(f"Failed to create conversation: {r.status_code} {r.text[:200]}")
        conversation_id = r.json()["id"]
        if verbose:
            print(f"[query_agent] Created conversation: {conversation_id}", file=sys.stderr)
    
    # Build message
    payload = {
        "system": "",
        "additionalContext": (
            "<page_context>\nRoute: /agents\nFeature: Agents\n</page_context>\n" + context
        ),
        "agentKey": agent_key,
        "clientTools": [],
        "messages": [{"role": "user", "content": [{"type": "text", "text": question}]}]
    }
    
    r2 = requests.post(
        f"{BASE}/internal/v1/conversations/{conversation_id}/messages",
        headers=hdrs,
        data=json.dumps(payload),
        timeout=120
    )
    
    if r2.status_code != 200:
        raise Exception(f"Agent query failed: {r2.status_code} {r2.text[:200]}")
    
    text = parse_sse(r2.text)
    if verbose:
        print(f"[query_agent] Response: {len(text)} chars", file=sys.stderr)
    
    return conversation_id, text


def build_kld_context():
    """Build a rich KLD business context string to inject into any agent call."""
    return """
<business_context>
Company: Kootenay Lawn Doctor (KLD)
Location: Cranbrook, BC, Canada (also serves Elk Valley - Fernie, Sparwood, Elkford)
Type: Residential lawn care company
Season: Year-round (snow removal + spring/summer/fall lawn services)

REVENUE (as of May 26, 2026 snapshot):
- Total waiting list revenue: $739,577
- Completed revenue: $471,071  
- Dispatched (in progress): $43,428
- Booked total: $514,499

TOP SERVICES BY CLIENT COUNT:
- MOWIN (weekly mowing, Cranbrook): 2,504 jobs, $180,299 — 14% complete
- ELKMOW (weekly mowing, Elk Valley): 1,957 jobs, $223,325 — 12% complete
- FW2 (fertilizer & weed control, 2-app): 1,465 clients, $204,740
- FW3 (fertilizer & weed control, 3-app): 1,228 clients, $158,088
- FW4 (fertilizer & weed control, 4-app): 1,155 clients, $146,324
- KICKSTART (spring cleanup): 280 jobs, $122,371 — 100% DONE
- FW1 (fertilizer, 1-app): 1,292 dispatched jobs, $174,112 — 87% done
- VGCTRL (vegetation control): 139 WL clients, $34,356
- IC/TURF (insect control): 126 WL clients, $16,370

PRICING (2026):
- Mowing: $50-80/visit (4,000-10,000 SF), weekly only
- FW4: $440 Cranbrook / $480 Bylaw (Kimberley/Fernie)
- Kickstart: $350+ (7 cents/SF Cranbrook, 8 cents Elk Valley)
- General Clean-Up: $90/hr
- Labour cost benchmark: $39/hr base + 9.4% burden = ~$42.67/hr true cost

TEAM:
- Office: Claudia Vinette (reception), Fiona Bedell (admin), Ethan St. Jean (ops manager)
- Field Supervisor: Phil Budiselich
- ~15 field staff across 4 crews
- 3 trucks: T-1 Walker, T-2 Walker, T-3 Kubota (mow); spray truck separate

OPERATIONS:
- CRM: Service AutoPilot (SAP)
- Bylaw communities (Kimberley, Fernie): use organic herbicide (Fiesta), 10-15% higher pricing
- Pre-pay discount: 10% before April 1
- No bi-weekly mowing policy
- Skip policy: crew discretion + 1 approved skip/client/month

KEY BOTTLENECKS:
- ELKMOW/MOWIN only 12-14% complete by June — large backlog
- GEN/CUL: 31/53 jobs still pending
- H/MOW: 39/55 still pending
</business_context>
"""


if __name__ == "__main__":
    if "--list" in sys.argv:
        list_agents()
        sys.exit(0)
    
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    
    agent_key = sys.argv[1]
    question  = sys.argv[2]
    context   = build_kld_context()
    
    print(f"Querying [{agent_key}]...\n", file=sys.stderr)
    cid, response = query_agent(agent_key, question, context=context, verbose=True)
    
    print(f"--- Conversation: {cid} ---")
    print(response)
