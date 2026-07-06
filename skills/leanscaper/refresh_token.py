#!/usr/bin/env python3
"""
LeanScaper JWT Auto-Refresh (v3 — email/password, no Google OAuth)
===================================================================
Flow:
  1. Navigate to auth.leanscaper.com/u/login
  2. Fill email (LEANSCAPER_EMAIL) + password (LEANSCAPER_PASSWORD)
  3. Click Continue
  4. If org picker appears, click "Kootenay Lawn Doctor Inc - 2"
  5. Navigate to token endpoint, extract JWT
  6. Write LEANSCAPER_JWT + LEANSCAPER_JWT_EXPIRES to /app/.agents/.env

Org routing is handled at API level via X-Organization-Id header
(see ls_auth.py), so the browser session just needs any valid login.

Usage:
    source /app/.agents/.env
    python3 /app/.agents/skills/leanscaper/refresh_token.py

Exit codes: 0=success, 1=failure
"""

import asyncio
import json
import os
import sys
import time
import websockets

BB_KEY       = os.environ.get("BROWSERBASE_API_KEY", "").strip()
LS_EMAIL     = os.environ.get("LEANSCAPER_EMAIL", "").strip()
LS_PASSWORD  = os.environ.get("LEANSCAPER_PASSWORD", "").strip()
ENV_FILE     = "/app/.agents/.env"

LOGIN_URL  = "https://auth.leanscaper.com/u/login"
TOKEN_URL  = "https://ai.leanscaper.com/auth/access-token?audience=https%3A%2F%2Fapi.leanscaper.com"


def write_token(token: str, expires_at: int):
    """Upsert LEANSCAPER_JWT and LEANSCAPER_JWT_EXPIRES in .agents/.env."""
    if not os.path.exists(ENV_FILE):
        with open(ENV_FILE, "w") as f:
            f.write(f"export LEANSCAPER_JWT='{token}'\n")
            f.write(f"export LEANSCAPER_JWT_EXPIRES={expires_at}\n")
        return

    lines = open(ENV_FILE).readlines()
    new_lines, found_jwt, found_exp = [], False, False
    for line in lines:
        if line.startswith(("export LEANSCAPER_JWT=", "LEANSCAPER_JWT=")):
            new_lines.append(f"export LEANSCAPER_JWT='{token}'\n"); found_jwt = True
        elif line.startswith(("export LEANSCAPER_JWT_EXPIRES=", "LEANSCAPER_JWT_EXPIRES=")):
            new_lines.append(f"export LEANSCAPER_JWT_EXPIRES={expires_at}\n"); found_exp = True
        elif line.startswith("LEANSCAPER_JWT=") and not line.startswith("export "):
            new_lines.append(f"export LEANSCAPER_JWT='{token}'\n"); found_jwt = True
        elif line.startswith("LEANSCAPER_JWT_EXPIRES=") and not line.startswith("export "):
            new_lines.append(f"export LEANSCAPER_JWT_EXPIRES={expires_at}\n"); found_exp = True
        else:
            new_lines.append(line)
    if not found_jwt:
        new_lines.append(f"export LEANSCAPER_JWT='{token}'\n")
    if not found_exp:
        new_lines.append(f"export LEANSCAPER_JWT_EXPIRES={expires_at}\n")
    open(ENV_FILE, "w").writelines(new_lines)


def get_page_ws() -> str:
    """Return the CDP websocket URL for the current Browserbase page."""
    import urllib.request, urllib.parse, re

    req = urllib.request.Request(
        "https://www.browserbase.com/v1/sessions?status=RUNNING",
        headers={"x-bb-api-key": BB_KEY},
        method="GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        sessions = data if isinstance(data, list) else data.get("data", [])
        if sessions:
            sid = sessions[0]["id"]
            req2 = urllib.request.Request(
                f"https://www.browserbase.com/v1/sessions/{sid}/debug",
                headers={"x-bb-api-key": BB_KEY},
                method="GET"
            )
            with urllib.request.urlopen(req2, timeout=10) as r2:
                debug = json.loads(r2.read())
            ws = debug.get("wsUrl") or debug.get("webSocketDebuggerUrl", "")
            if ws:
                return ws
            url_str = debug.get("debuggerFullscreenUrl", "")
            match = re.search(r"wss=([^&\"]+)", url_str)
            if match:
                return urllib.parse.unquote(match.group(1))
    except Exception as e:
        print(f"Warning: could not list sessions: {e}", file=sys.stderr)

    return ""


async def login_and_get_token(page_ws: str) -> tuple[str, int]:
    """
    Email/password login flow via CDP. Returns (token, expires_at) or ("", 0) on failure.
    """
    async with websockets.connect(
        page_ws,
        additional_headers={"x-bb-api-key": BB_KEY},
        ping_interval=None,
        max_size=10_000_000,
    ) as ws:
        msg_id = [1]

        async def send(method, params={}):
            mid = msg_id[0]; msg_id[0] += 1
            await ws.send(json.dumps({"id": mid, "method": method, "params": params}))
            while True:
                r = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
                if r.get("id") == mid:
                    return r

        async def js(expr):
            r = await send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            return r.get("result", {}).get("result", {}).get("value")

        async def click_xy(x, y):
            await send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
            await send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})

        async def type_text(text):
            for char in text:
                await send("Input.dispatchKeyEvent", {
                    "type": "keyDown", "key": char,
                    "text": char, "unmodifiedText": char
                })
                await send("Input.dispatchKeyEvent", {
                    "type": "keyUp", "key": char
                })

        await send("Page.enable")

        # ── Step 1: Check if already authenticated ───────────────────────────
        print("Step 1: Checking existing session...")
        await send("Page.navigate", {"url": TOKEN_URL})
        await asyncio.sleep(3)
        raw = await js("document.body.innerText")
        if raw and '"token"' in raw:
            try:
                d = json.loads(raw)
                if d.get("token"):
                    print("  ✅ Already authenticated — no login needed")
                    return d["token"], d.get("expires_at", 0)
            except Exception:
                pass

        # ── Step 2: Navigate to login page ──────────────────────────────────
        print("Step 2: Navigating to LeanScaper login...")
        await send("Page.navigate", {"url": LOGIN_URL})
        await asyncio.sleep(3)

        # ── Step 3: Fill email + password ───────────────────────────────────
        print("Step 3: Filling email + password...")

        # Fill email (input[name="username"] or first visible text input)
        email_js = f"""
(function() {{
    var inp = document.querySelector('input[name="username"]') ||
              document.querySelector('input[type="text"]:not([type="hidden"])') ||
              document.querySelectorAll('input:not([type="hidden"])')[0];
    if (inp) {{
        inp.focus();
        inp.value = '';
        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeInputValueSetter.call(inp, '{LS_EMAIL}');
        inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
        inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
        return 'ok';
    }}
    return 'no input found';
}})()"""
        result = await js(email_js)
        print(f"  Email: {result}")
        await asyncio.sleep(0.5)

        # Fill password (input[type="password"])
        pwd_js = f"""
(function() {{
    var inp = document.querySelector('input[type="password"]');
    if (inp) {{
        inp.focus();
        inp.value = '';
        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeInputValueSetter.call(inp, '{LS_PASSWORD}');
        inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
        inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
        return 'ok';
    }}
    return 'no password input found';
}})()"""
        result = await js(pwd_js)
        print(f"  Password: {result}")
        await asyncio.sleep(0.5)

        # ── Step 4: Click Continue ──────────────────────────────────────────
        print("Step 4: Clicking Continue...")
        continue_btn = await js("""
(function() {
    var btn = document.querySelector('button[type="submit"]') ||
              document.querySelector('button[name="action"]') ||
              Array.from(document.querySelectorAll('button')).find(b => /continue/i.test(b.textContent));
    if (btn) { var r = btn.getBoundingClientRect(); return JSON.stringify({x: r.x+r.width/2, y: r.y+r.height/2}); }
    return null;
})()""")
        if continue_btn:
            rect = json.loads(continue_btn)
            await click_xy(rect["x"], rect["y"])
            print("  Clicked Continue")
        else:
            print("  WARNING: Continue button not found")
        await asyncio.sleep(4)

        # ── Step 5: Handle org picker (if it appears) ───────────────────────
        for attempt in range(10):
            url = await js("location.href")
            body_text = await js("document.body.innerText") or ""
            print(f"  [{attempt*2}s] {url[:80]}")

            if "ai.leanscaper.com" in url and "auth" not in url:
                print("  ✅ Redirected to LeanScaper — login successful")
                break
            if "kootenay" in body_text.lower() and "multiple companies" in body_text.lower():
                print("  ✅ Org picker visible — selecting KLD Inc - 2")
                # Click the "Kootenay Lawn Doctor Inc - 2" button
                kld_rect = await js("""
(function() {
    var all = Array.from(document.querySelectorAll('button, a, [role="button"]'));
    var kld = all.find(el => /kootenay.*inc.*-.*2/i.test(el.textContent));
    if (kld) {
        var r = kld.getBoundingClientRect();
        return JSON.stringify({x: r.x+r.width/2, y: r.y+r.height/2, text: kld.textContent.trim().substring(0,50)});
    }
    return null;
})()""")
                if kld_rect:
                    rect = json.loads(kld_rect)
                    print(f"  Clicking: {rect['text']}")
                    await click_xy(rect["x"], rect["y"])
                    await asyncio.sleep(4)
                break
            await asyncio.sleep(2)

        # ── Step 6: Extract JWT from token endpoint ─────────────────────────
        print("Step 6: Fetching JWT from token endpoint...")
        await send("Page.navigate", {"url": TOKEN_URL})
        await asyncio.sleep(3)
        raw = await js("document.body.innerText")
        if raw and '"token"' in raw:
            try:
                d = json.loads(raw)
                if d.get("token"):
                    print("  ✅ JWT extracted successfully")
                    return d["token"], d.get("expires_at", 0)
            except Exception as e:
                print(f"  ❌ JSON parse error: {e}")

        print("  ❌ Could not extract JWT")
        return "", 0


def main():
    if not BB_KEY:
        print("❌ BROWSERBASE_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    if not LS_EMAIL or not LS_PASSWORD:
        print("❌ LEANSCAPER_EMAIL or LEANSCAPER_PASSWORD not set", file=sys.stderr)
        sys.exit(1)

    current_token = os.environ.get("LEANSCAPER_JWT", "")
    current_exp   = int(os.environ.get("LEANSCAPER_JWT_EXPIRES", "0"))
    now           = int(time.time())

    if current_token and current_exp > now + 3600:
        remaining_h = (current_exp - now) / 3600
        print(f"✅ JWT still valid ({remaining_h:.1f}h remaining) — no refresh needed")
        sys.exit(0)

    print("🔄 Refreshing LeanScaper JWT via email/password login...")
    ws = get_page_ws()
    if not ws:
        print("❌ Could not get Browserbase websocket URL", file=sys.stderr)
        sys.exit(1)

    token, expires_at = asyncio.run(login_and_get_token(ws))
    if not token:
        print("❌ Login failed — could not get JWT", file=sys.stderr)
        sys.exit(1)

    write_token(token, expires_at)
    remaining_h = (expires_at - now) / 3600 if expires_at else 24
    print(f"\n✅ LEANSCAPER_JWT updated in {ENV_FILE}")
    print(f"   Expires in {remaining_h:.1f}h")
    sys.exit(0)


if __name__ == "__main__":
    main()
