"""
LeanScaper Auth — email/password login + X-Organization-Id header for org routing.

Auth flow:
  1. Navigate to auth.leanscaper.com/u/login
  2. Fill email + password (from LEANSCAPER_EMAIL / LEANSCAPER_PASSWORD env vars)
  3. Click Continue
  4. If org picker appears, click "Kootenay Lawn Doctor Inc - 2"
  5. Navigate to token endpoint, extract JWT
  6. Use X-Organization-Id header to route API calls to KLD Inc - 2

Env vars (in .agents/.env):
  LEANSCAPER_EMAIL      — login email
  LEANSCAPER_PASSWORD   — login password
  LEANSCAPER_ORG_UUID   — 09c7c652-a7c7-492e-a65b-759db4ddba45 (KLD Inc - 2)
  LEANSCAPER_JWT        — current JWT (auto-refreshed)

Usage:
    from ls_auth import get_ls_token, ls_internal_get, ls_internal_post, ask_lana
    token = get_ls_token(page)  # from authenticated Playwright page
"""
import json, os, time

LS_TOKEN_URL   = "https://ai.leanscaper.com/auth/access-token?audience=https%3A%2F%2Fapi.leanscaper.com"
LS_API_BASE    = "https://api.leanscaper.com"
LS_FRONT_BASE  = "https://ai.leanscaper.com"
LS_ORG_UUID    = os.environ.get("LEANSCAPER_ORG_UUID", "09c7c652-a7c7-492e-a65b-759db4ddba45")

def _org_headers(token: str) -> dict:
    """Build auth headers with org routing."""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Organization-Id": LS_ORG_UUID,
    }

def get_ls_token(page) -> str:
    """Get Bearer token from an already-authenticated Playwright page."""
    result = page.evaluate(f"""
        async () => {{
            const r = await fetch('{LS_TOKEN_URL}', {{credentials: 'include'}});
            const d = await r.json();
            return d.token || null;
        }}
    """)
    if not result:
        raise RuntimeError("LeanScaper token fetch returned null — session may be expired")
    return result


def ls_get(page, path: str) -> dict:
    """GET a LeanScaper /api/* endpoint using browser credentials."""
    url = f"{LS_FRONT_BASE}{path}" if path.startswith("/api") else f"{LS_FRONT_BASE}{path}"
    result = page.evaluate(f"""
        async () => {{
            const r = await fetch('{url}', {{credentials: 'include'}});
            return await r.json();
        }}
    """)
    return result


def ls_internal_get(page, path: str) -> dict:
    """GET a LeanScaper /internal/v1/* endpoint using Bearer token + org header."""
    token = get_ls_token(page)
    org_uuid = LS_ORG_UUID
    result = page.evaluate(f"""
        async ([token, orgUuid]) => {{
            const r = await fetch('{LS_API_BASE}{path}', {{
                headers: {{
                    'Authorization': 'Bearer ' + token,
                    'X-Organization-Id': orgUuid
                }}
            }});
            return await r.json();
        }}
    """, [token, org_uuid])
    return result


def ls_internal_post(page, path: str, body: dict) -> dict:
    """POST to a LeanScaper /internal/v1/* endpoint using Bearer token + org header."""
    token = get_ls_token(page)
    body_str = json.dumps(body)
    org_uuid = LS_ORG_UUID
    result = page.evaluate(f"""
        async ([token, orgUuid, bodyStr]) => {{
            const r = await fetch('{LS_API_BASE}{path}', {{
                method: 'POST',
                headers: {{
                    'Authorization': 'Bearer ' + token,
                    'Content-Type': 'application/json',
                    'X-Organization-Id': orgUuid
                }},
                body: bodyStr
            }});
            return {{ status: r.status, body: await r.text() }};
        }}
    """, [token, org_uuid, body_str])
    return result


def ask_lana(page, question: str, context: str = "") -> str:
    """
    Ask Lana a question with optional context. Returns the full response text.
    Uses the verified SSE streaming pattern (obj.delta field).
    Routes to KLD Inc - 2 via X-Organization-Id header.
    """
    token = get_ls_token(page)
    org_uuid = LS_ORG_UUID
    full_question = f"{context}\n\n{question}" if context else question

    JS = """
    async ([token, question, orgUuid]) => {
        const convR = await fetch('https://api.leanscaper.com/internal/v1/conversations', {
            method: 'POST',
            headers: {
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json',
                'X-Organization-Id': orgUuid
            },
            body: JSON.stringify({ agentId: 'leanscaperos' })
        });
        const conv = await convR.json();

        const msgR = await fetch('https://api.leanscaper.com/internal/v1/conversations/' + conv.id + '/messages', {
            method: 'POST',
            headers: {
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json',
                'X-Organization-Id': orgUuid
            },
            body: JSON.stringify({
                system: '', additionalContext: '', agentKey: 'leanscaperos',
                conversationId: conv.id, clientTools: [],
                messages: [{ role: 'user', content: question }]
            })
        });

        const reader = msgR.body.getReader();
        const decoder = new TextDecoder();
        let text = '';
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value);
            for (const line of chunk.split('\\n')) {
                if (!line.startsWith('data:')) continue;
                try {
                    const obj = JSON.parse(line.slice(5).trim());
                    if (obj.delta) text += obj.delta;
                } catch(e) {}
            }
        }
        return { text, cid: conv.id };
    }
    """
    result = page.evaluate(JS, [token, full_question, org_uuid])
    return result.get("text", "")
