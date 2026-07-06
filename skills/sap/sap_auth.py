"""
sap_auth.py — SAP Authentication Module (KLD)
Version: 3.0 — Unified 3-Tier Architecture
=============================================

WHY THIS EXISTS:
  SAP (my.serviceautopilot.com) is protected by Incapsula (Imperva WAF).
  Raw HTTP requests from Python are detected and blocked — even with correct cookies.
  The ONLY way to make SAP API calls from scripts is with cookies from a REAL Chrome browser.

FOUR-TIER ARCHITECTURE:
  ─────────────────────────────────────────────────────────────────────
  TIER 0 — Base44-Hosted Browserbase (Interactive agent only)
    Used when: Doc agent is running interactively via Base44 platform
    Method:    agent browserbase_navigate() / browserbase_screenshot() / etc.
    NOTE:      Do NOT use standalone Browserbase API keys. The Base44 platform
               provides Browserbase for FREE via its built-in tools. Never set
               BROWSERBASE_API_KEY in .env — that points to a paid personal account.

  TIER 1 — Agent Direct (no API key needed)
    Used when: Doc agent is running interactively
    Method:    browserbase_navigate() + javascript: URI fetch
    Pattern:   build_js_call(endpoint, body) → execute via agent tool
    Result:    document.title set to SAPRESULT::{json} or SAPERR::{msg}

  TIER 2 — Cookie Replay (scripts, no Playwright needed)
    Used when: Automation scripts run, fresh cookies exist
    Method:    Load cookies from /tmp/sap_cookies.json into requests.Session
               + spoofed Chrome UA + SAP-expected headers
    Cookie TTL: 4 hours (SAP session expires ~8h but we refresh conservatively)
    Refresh:   Agent refreshes cookies before launching any SAP script

  TIER 3 — Headless Login (scripts, fresh Playwright login)
    Used when: Cookie cache is empty/stale, scripts need to run
    Method:    Playwright headless Chromium → login → extract cookies → save
    Requirements: SAP_USERNAME + SAP_PASSWORD in .env (both confirmed present)
  ─────────────────────────────────────────────────────────────────────

PUBLIC API:
  get_sap_session()       → requests.Session-compatible object (Tier 2 → Tier 3)
  get_sap_page()          → (playwright, browser, page) for complex Playwright ops
  sap_call(path, body)    → dict — single API call, auto-picks best tier
  SAP_BASE                → "https://my.serviceautopilot.com"
  refresh_cookies()       → force a fresh Playwright login + save cookies
  save_agent_cookies(lst) → save cookie list extracted from agent Browserbase session

AGENT PATTERN (Tier 1):
  from sap_auth import build_js_call, parse_js_result
  js = build_js_call('/WebServices/PayrollWs.asmx/GetPayrollWageReport', body)
  # → agent calls: browserbase_navigate(js)
  # → agent calls: browserbase_get_content(selector='title')
  # → agent calls: parse_js_result(title)

COOKIE CACHE:
  /tmp/sap_cookies.json — {"saved_at": epoch, "cookies": [...]}
  Refresh by: agent running before scripts, OR refresh_cookies() Playwright call
"""

import json, os, sys, time
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────────────

SAP_BASE      = "https://my.serviceautopilot.com"
SAP_LOGIN_URL = f"{SAP_BASE}/UserLogin.aspx"
SAP_HOME_URL  = f"{SAP_BASE}/Home.aspx"

SAP_EMAIL    = os.environ.get("SAP_USERNAME", "ethan@kootenaylawndoctor.com")
SAP_PASSWORD = os.environ.get("SAP_PASSWORD", "")

COOKIE_FILE  = "/tmp/sap_cookies.json"
COOKIE_TTL   = 4 * 3600   # 4 hours — conservative; SAP session is ~8h

# Chrome 124 UA — must match what Browserbase actually sends
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

COMMON_HEADERS = {
    "Content-Type":    "application/json; charset=utf-8",
    "X-Requested-With": "XMLHttpRequest",
    "Origin":          SAP_BASE,
    "Referer":         SAP_HOME_URL,
    "User-Agent":      UA,
}

# ── Tier 1: Agent-direct JS fetch helpers ────────────────────────────────────

def build_js_call(endpoint: str, body: dict, max_chars: int = 3000) -> str:
    """
    Build a javascript: URI that executes a SAP API call in-browser.
    Result is written to document.title as SAPRESULT::{json} or SAPERR::{msg}.

    Usage (agent):
        js = build_js_call('/WebServices/PayrollWs.asmx/GetPayrollWageReport', body)
        browserbase_navigate(js)
        title = browserbase_get_content(selector='title')
        result = parse_js_result(title)
    """
    body_js = json.dumps(json.dumps(body))  # double-encode: outer for JS string literal
    max_chars_str = str(max_chars)
    ep = endpoint.replace("'", "\\'")
    return (
        f"javascript:void("
        f"fetch('{ep}',{{method:'POST',"
        f"headers:{{'Content-Type':'application/json; charset=utf-8','X-Requested-With':'XMLHttpRequest'}},"
        f"body:{body_js}}})"
        f".then(r=>r.text())"
        f".then(t=>{{try{{var d=JSON.parse(t);document.title='SAPRESULT::'+JSON.stringify(d).substring(0,{max_chars_str})}}catch(e){{document.title='SAPERR::parse:'+t.substring(0,200)}}}})"
        f".catch(e=>document.title='SAPERR::'+e.message)"
        f")"
    )


def parse_js_result(title: str) -> dict:
    """
    Parse the document.title set by build_js_call().
    Returns the parsed JSON dict (the 'd' key is unwrapped automatically).
    Raises RuntimeError on error.
    """
    if not title:
        raise RuntimeError("Empty title — SAP JS call may not have completed yet")
    if title.startswith("SAPRESULT::"):
        raw = json.loads(title[len("SAPRESULT::"):])
        return raw.get("d", raw) if isinstance(raw, dict) and "d" in raw else raw
    elif title.startswith("SAPERR::"):
        raise RuntimeError(f"SAP fetch error: {title[8:]}")
    else:
        raise RuntimeError(f"Unexpected title (JS may not have run): {repr(title[:100])}")


# ── Cookie cache (Tier 2) ─────────────────────────────────────────────────────

def load_cookies() -> list | None:
    """Load cached SAP cookies. Returns None if missing or expired."""
    path = Path(COOKIE_FILE)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        age = time.time() - data.get("saved_at", 0)
        if age > COOKIE_TTL:
            print(f"[sap_auth] Cookie cache expired ({age/3600:.1f}h old)", flush=True)
            return None
        cookies = data.get("cookies", [])
        if not cookies:
            return None
        print(f"[sap_auth] ✅ Loaded {len(cookies)} cached cookies ({age/60:.0f}m old)", flush=True)
        return cookies
    except Exception as e:
        print(f"[sap_auth] Cookie load error: {e}", flush=True)
        return None


def save_cookies(cookies: list):
    """Save SAP cookies to cache file."""
    data = {"saved_at": time.time(), "cookies": cookies}
    Path(COOKIE_FILE).write_text(json.dumps(data, indent=2))
    print(f"[sap_auth] Saved {len(cookies)} cookies to {COOKIE_FILE}", flush=True)


def save_agent_cookies(cookies: list):
    """
    Save cookies extracted from the agent's Browserbase session.
    Call this after any agent-driven SAP navigation to keep the cache fresh.

    cookies: list of dicts with keys: name, value, domain, path, expires, etc.
             (format returned by Playwright context.cookies() or CDP)
    """
    # Normalize — keep only SAP-relevant cookies
    sap_cookies = [
        c for c in cookies
        if any(d in c.get("domain", "") for d in ["serviceautopilot.com", "incapsula.com"])
    ]
    if not sap_cookies:
        print("[sap_auth] ⚠ No SAP-relevant cookies in provided list", flush=True)
        return
    save_cookies(sap_cookies)


def cookie_age_minutes() -> float | None:
    """Return age of cookie cache in minutes, or None if no cache."""
    path = Path(COOKIE_FILE)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return (time.time() - data.get("saved_at", 0)) / 60
    except Exception:
        return None



# ── Tier 0: Browserbase Cloud Login ─────────────────────────────────────────

BB_API_KEY    = os.environ.get("BROWSERBASE_API_KEY", "")
BB_PROJECT_ID = os.environ.get("BROWSERBASE_PROJECT_ID", "d17e9dc8-9693-4a0f-b1dd-5275dc0af9c5")


def _browserbase_fresh_login() -> list:
    """
    Login to SAP via Browserbase Cloud (Tier 0).
    Creates a remote Browserbase session, connects via CDP + Playwright,
    logs in, extracts cookies, closes the session.
    Activated automatically when BROWSERBASE_API_KEY is set.
    Returns cookie list (same format as refresh_cookies / Tier 3).
    """
    import requests as _req
    from playwright.sync_api import sync_playwright

    print("[sap_auth] 🌐 Using Browserbase Cloud for SAP login...", flush=True)

    # Create Browserbase session
    r = _req.post(
        "https://www.browserbase.com/v1/sessions",
        headers={"x-bb-api-key": BB_API_KEY, "Content-Type": "application/json"},
        json={"projectId": BB_PROJECT_ID, "browserSettings": {"viewport": {"width": 1920, "height": 1080}}},
        timeout=30,
    )
    r.raise_for_status()
    session_data = r.json()
    session_id   = session_data["id"]
    connect_url  = session_data["connectUrl"]
    print(f"[sap_auth] 🌐 Browserbase session created: {session_id}", flush=True)

    cookies = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(connect_url)
            ctx  = browser.contexts[0]
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            page.goto(SAP_LOGIN_URL, wait_until="domcontentloaded", timeout=40000)
            time.sleep(2)
            page.fill("#txtLogin", SAP_EMAIL)
            page.fill("#txtPassword", SAP_PASSWORD)
            page.click("#loginbtn")

            try:
                page.wait_for_url("**/Home.aspx", timeout=25000)
            except Exception:
                page.wait_for_function(
                    "() => !window.location.href.includes('UserLogin')",
                    timeout=15000,
                )

            print(f"[sap_auth] ✅ Browserbase login complete: {page.url}", flush=True)
            time.sleep(2)
            cookies = ctx.cookies()
            browser.close()

    finally:
        # Always release the session
        try:
            _req.post(
                f"https://www.browserbase.com/v1/sessions/{session_id}",
                headers={"x-bb-api-key": BB_API_KEY, "Content-Type": "application/json"},
                json={"status": "REQUEST_RELEASE"},
                timeout=10,
            )
            print(f"[sap_auth] 🌐 Browserbase session released: {session_id}", flush=True)
        except Exception:
            pass

    if not cookies:
        raise RuntimeError("[sap_auth] Browserbase login returned 0 cookies")

    save_cookies(cookies)
    print(f"[sap_auth] ✅ Saved {len(cookies)} cookies from Browserbase Cloud", flush=True)
    return cookies


# ── Tier 3: Playwright fresh login ───────────────────────────────────────────

def refresh_cookies() -> list:
    """
    Login to SAP and save fresh cookies.
    Tier 0: Uses Browserbase Cloud if BROWSERBASE_API_KEY is set (GitHub Actions, zero local deps).
    Tier 3: Falls back to local Playwright headless Chromium.
    Returns the cookie list.
    """
    if not SAP_PASSWORD:
        raise RuntimeError("[sap_auth] SAP_PASSWORD not set in environment")

    # Tier 0 — Browserbase Cloud (preferred in CI/GitHub Actions)
    # Tier 0 (Base44-hosted Browserbase) is only available when the agent
    # calls browserbase_navigate() directly. For script-based refresh, use Tier 3.
    # Never use standalone BB API keys.

    print("[sap_auth] 🔄 Running local Playwright headless login (Tier 3)...", flush=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "[sap_auth] playwright not installed. Run: pip install playwright && python3 -m playwright install chromium"
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=UA,
            locale="en-CA",
        )
        page = ctx.new_page()

        # Navigate to login
        page.goto(SAP_LOGIN_URL, wait_until="domcontentloaded", timeout=40000)
        time.sleep(2)

        # Fill credentials
        page.fill("#txtLogin", SAP_EMAIL)
        page.fill("#txtPassword", SAP_PASSWORD)
        page.click("#loginbtn")

        # Wait for successful login
        try:
            page.wait_for_url("**/Home.aspx", timeout=25000)
        except Exception:
            # Try waiting for any non-login URL
            try:
                page.wait_for_function(
                    "() => !window.location.href.includes('UserLogin')",
                    timeout=15000
                )
            except Exception:
                browser.close()
                raise RuntimeError(f"[sap_auth] Login failed — still at: {page.url}")

        print(f"[sap_auth] ✅ Logged in at: {page.url}", flush=True)
        time.sleep(2)  # Let SAP React app settle

        # Extract cookies
        cookies = ctx.cookies()
        browser.close()

        save_cookies(cookies)
        print(f"[sap_auth] ✅ Saved {len(cookies)} fresh cookies", flush=True)
        return cookies


# ── Tier 2: Cookie-based requests.Session ────────────────────────────────────

class SAPSession:
    """
    requests.Session-compatible wrapper that uses cached browser cookies.
    Automatically falls back to Playwright login if cookies are stale.

    Supports: .post(url, data=..., json=..., headers=..., timeout=...)
              .get(url, headers=..., timeout=...)

    All calls are routed through the real requests library with proper
    Chrome-spoofed headers + Incapsula bypass cookies.
    """

    def __init__(self, force_refresh: bool = False):
        import requests as _req
        self._req = _req
        self._sess = _req.Session()
        self._sess.headers.update(COMMON_HEADERS)
        self._init_cookies(force_refresh)

    def _init_cookies(self, force_refresh: bool):
        cookies = None if force_refresh else load_cookies()
        if cookies is None:
            cookies = refresh_cookies()
        self._apply_cookies(cookies)

    def _apply_cookies(self, cookies: list):
        """Load a cookie list (Playwright format) into requests.Session."""
        import requests as _req
        jar = self._req.cookies.RequestsCookieJar()
        for c in cookies:
            jar.set(
                name=c.get("name", ""),
                value=c.get("value", ""),
                domain=c.get("domain", "").lstrip("."),
                path=c.get("path", "/"),
            )
        self._sess.cookies = jar
        print(f"[sap_auth] Applied {len(cookies)} cookies to session", flush=True)

    def _auto_refresh_on_error(self, resp):
        """Check if response looks like a session expiry; refresh if so."""
        if resp.status_code in (302, 401, 403):
            return True
        text = resp.text[:200] if hasattr(resp, 'text') else ""
        if "UserLogin" in text or "login" in text.lower() or text.strip().startswith("<!DOCTYPE"):
            return True
        return False

    def _make_request(self, method: str, url: str, **kwargs) -> "_MockResponse":
        """Execute request, auto-refresh cookies if session expired."""
        # Make URL absolute
        if url.startswith("/"):
            url = SAP_BASE + url

        resp = getattr(self._sess, method)(url, **kwargs)

        if self._auto_refresh_on_error(resp):
            print(f"[sap_auth] Session appears expired (status={resp.status_code}), refreshing...", flush=True)
            cookies = refresh_cookies()
            self._apply_cookies(cookies)
            resp = getattr(self._sess, method)(url, **kwargs)

        return resp

    def post(self, url, data=None, json=None, headers=None, timeout=30, **kwargs):
        if headers:
            # Merge with defaults (caller headers take priority)
            merged = {**COMMON_HEADERS, **headers}
            self._sess.headers.update(merged)
        kw = {"timeout": timeout, **kwargs}
        if data is not None:
            kw["data"] = data
        if json is not None:
            kw["json"] = json
        return self._make_request("post", url, **kw)

    def get(self, url, headers=None, timeout=30, **kwargs):
        if headers:
            merged = {**COMMON_HEADERS, **headers}
            self._sess.headers.update(merged)
        return self._make_request("get", url, timeout=timeout, **kwargs)

    @property
    def cookies(self):
        return self._sess.cookies


# ── Playwright page helper (for complex multi-step ops) ───────────────────────

def get_sap_page():
    """
    Returns (playwright, browser, page) with an active SAP session via Playwright.

    IMPORTANT: Caller must close when done:
        browser.close()
        p.stop()   (if using sync_playwright context directly)

    Prefers loading existing cookies for speed. Falls back to fresh login.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("[sap_auth] playwright not installed")

    p = sync_playwright().start()
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
    )
    ctx = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent=UA,
        locale="en-CA",
    )
    page = ctx.new_page()

    # Try with cached cookies first
    cookies = load_cookies()
    if cookies:
        ctx.add_cookies(cookies)
        page.goto(SAP_HOME_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        if "UserLogin" in page.url or "login" in page.url.lower():
            print("[sap_auth] Cached cookies expired, logging in fresh...", flush=True)
            browser.close()
            p.stop()
            return _playwright_fresh_login()

        print(f"[sap_auth] ✅ Playwright session active via cached cookies: {page.url}", flush=True)
        # Refresh cookie cache from this session
        save_cookies(ctx.cookies())
        return p, browser, page
    else:
        # No cookies — need fresh login
        browser.close()
        p.stop()
        return _playwright_fresh_login()


def _playwright_fresh_login():
    """Full Playwright headless login. Returns (p, browser, page)."""
    from playwright.sync_api import sync_playwright

    p = sync_playwright().start()
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
    )
    ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent=UA, locale="en-CA")
    page = ctx.new_page()

    page.goto(SAP_LOGIN_URL, wait_until="domcontentloaded", timeout=40000)
    time.sleep(2)
    page.fill("#txtLogin", SAP_EMAIL)
    page.fill("#txtPassword", SAP_PASSWORD)
    page.click("#loginbtn")
    page.wait_for_url("**/Home.aspx", timeout=25000)
    time.sleep(2)

    print(f"[sap_auth] ✅ Playwright fresh login complete: {page.url}", flush=True)
    save_cookies(ctx.cookies())
    return p, browser, page


# ── Convenience: single API call ─────────────────────────────────────────────

def sap_call(path: str, body: dict, seed_url: str = None, retries: int = 2) -> dict:
    """
    Make a single SAP API call. Best for quick one-off lookups.

    Uses Tier 2 (cookie session) by default.
    Falls back to Playwright (Tier 3) on failure.

    Args:
        path:     SAP endpoint path (e.g. '/WebServices/PayrollWs.asmx/GetPayrollWageReport')
        body:     Request body dict
        seed_url: If provided, navigates to this page first to seed session state
                  (some endpoints require prior page nav — e.g. /Timesheets.aspx)
        retries:  Number of retry attempts

    Returns:
        dict — parsed response (the 'd' key is unwrapped automatically)
    """
    for attempt in range(retries):
        try:
            sess = SAPSession(force_refresh=(attempt > 0))

            if seed_url:
                # Navigate to seed page to establish session context
                seed_full = (SAP_BASE + seed_url) if seed_url.startswith("/") else seed_url
                seed_resp = sess.get(seed_full, timeout=20)
                if "UserLogin" in seed_resp.text[:200]:
                    raise RuntimeError("Seed page redirected to login")

            resp = sess.post(
                SAP_BASE + path,
                data=json.dumps(body),
                headers=COMMON_HEADERS,
                timeout=30
            )
            result = resp.json()
            return result.get("d", result) if isinstance(result, dict) and "d" in result else result

        except Exception as e:
            print(f"[sap_auth] sap_call attempt {attempt + 1} failed: {e}", flush=True)
            if attempt < retries - 1:
                time.sleep(3)
            else:
                raise


# ── Legacy compatibility shim ─────────────────────────────────────────────────

def get_sap_session(force_refresh: bool = False) -> SAPSession:
    """
    Get an authenticated SAP session. Drop-in replacement for old requests.Session usage.
    Supports: .post(url, data=..., headers=..., timeout=...) and .get(url)
    """
    return SAPSession(force_refresh=force_refresh)


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("sap_auth.py v3.0 — Self-test")
    print("=" * 60)

    # Show cookie cache status
    age = cookie_age_minutes()
    if age is not None:
        print(f"Cookie cache: {age:.0f} minutes old")
    else:
        print("Cookie cache: empty — will run Playwright login")

    # Test Tier 3 → Tier 2 flow
    print("\n[1] Getting SAP session...")
    sess = get_sap_session()
    print("[1] ✅ Session ready")

    # Test a simple, fast endpoint
    print("\n[2] Testing GetPayrollWageReport...")
    import datetime
    today = datetime.date.today()
    body = {"Input": {
        "StartDate": {"Month": today.month, "Day": today.day, "Year": today.year},
        "EndDate":   {"Month": today.month, "Day": today.day, "Year": today.year},
        "RemoveTimelessResources": False,
        "TagIDs": [], "ResourceIDs": []
    }}
    resp = sess.post(f"{SAP_BASE}/WebServices/PayrollWs.asmx/GetPayrollWageReport",
                     data=json.dumps(body), headers=COMMON_HEADERS, timeout=30)
    result = resp.json()
    resources = result.get("d", {}).get("ResourceItems", [])
    print(f"[2] ✅ {len(resources)} resources returned")

    # Show Tier 1 agent pattern
    print("\n[3] Tier 1 JS call pattern (for agent use):")
    js = build_js_call("/WebServices/PayrollWs.asmx/GetPayrollWageReport", body)
    print(f"  JS length: {len(js)} chars")
    print(f"  First 100: {js[:100]}...")
    print("[3] ✅ build_js_call works")

    print("\n✅ sap_auth.py v3.0 self-test passed")
