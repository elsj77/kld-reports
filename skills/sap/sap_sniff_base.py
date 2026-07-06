#!/usr/bin/env python3
"""
sap_sniff_base.py — Reusable base module for SAP endpoint sniffing scripts.

Import this instead of rewriting stealth/login/fetch boilerplate every round.

Usage in a sniff script:
    from sap_sniff_base import SniffSession

    sniff = SniffSession('r8a')

    with sniff as page:
        sniff.log("Starting R8a...")

        ok, raw, payload = sniff.try_endpoint(page, '/WebServices/SomeWs.asmx/Method', [{}])
        if ok:
            sniff.cracked('Method', raw)

    sniff.summary()

Run with:
    sap_sniff.sh launch .agents/skills/sap/deep_sniff_r8a.py sniff8a
    sap_sniff.sh status sniff8a
"""
import sys, json, time, re, os
sys.path.insert(0, '/app/.agents/skills/sap')

# Auth — matches sap_auth.py conventions
SAP_BASE = 'https://my.serviceautopilot.com'
SAP_USERNAME = os.environ.get('SAP_USERNAME', os.environ.get('SAP_EMAIL', 'ethan@kootenaylawndoctor.com'))
SAP_PASSWORD = os.environ.get('SAP_PASSWORD', '')
SAP_LOGIN_URL = f'{SAP_BASE}/UserLogin.aspx'

# Test client GUID (Ethan St Jean — safety lock)
DEFAULT_TC = 'c6577811-7cf8-42c2-b69d-44ae0ddec633'


class SniffSession:
    """Manages a full SAP sniffing session with tmux-friendly output."""

    def __init__(self, round_name, TC=None, headless=True):
        self.round_name = round_name
        self.TC = TC or DEFAULT_TC
        self.headless = headless
        self.progress_file = f'/tmp/sap_sniff_{round_name}_progress.txt'
        self.results_file = f'/tmp/sap_sniff_{round_name}_results.json'
        self.captured_requests = []
        self.cracked_endpoints = []
        self.failed_endpoints = []
        self._page = None
        self._browser = None
        self._ctx = None
        self._playwright = None
        self._listener_attached = False

        # Clear progress
        with open(self.progress_file, 'w') as f:
            pass

    def log(self, msg):
        """Log a message to both stdout and progress file."""
        ts = time.strftime('%H:%M:%S')
        line = f"[{ts}] {msg}"
        print(line, flush=True)
        with open(self.progress_file, 'a') as f:
            f.write(line + '\n')

    def _get_stealth(self):
        """Create a configured Stealth instance."""
        from playwright_stealth import Stealth
        return Stealth(
            navigator_webdriver=True,
            chrome_runtime=True,
            navigator_user_agent=True,
            navigator_platform=True,
            navigator_languages=True,
            webgl_vendor=True,
            navigator_user_agent_override="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.207 Safari/537.36",
            navigator_platform_override="Win32",
        )

    def login(self, page):
        """Perform SAP login on the given page."""
        self.log("Logging into SAP...")
        page.goto(SAP_LOGIN_URL, wait_until="domcontentloaded", timeout=40000)
        time.sleep(2)
        page.fill("#txtLogin", SAP_USERNAME)
        page.fill("#txtPassword", SAP_PASSWORD)
        page.click("#loginbtn")
        time.sleep(5)
        # Check if we're past the login page
        for _ in range(10):
            current_url = page.url
            if 'Home.aspx' in current_url or 'UserLogin' not in current_url:
                break
            time.sleep(2)
        self.log(f"Login complete: {page.url}")
        time.sleep(3)

    def __enter__(self):
        """Start Playwright, create stealth page, login."""
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"]
        )
        self._ctx = self._browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.207 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/Edmonton"
        )
        self._page = self._ctx.new_page()
        stealth = self._get_stealth()
        stealth.use_sync(self._page)
        self.login(self._page)
        return self._page

    def __exit__(self, *args):
        """Cleanup Playwright."""
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    @property
    def page(self):
        return self._page

    def fetch(self, page, endpoint, payload):
        """
        Execute a fetch() call from within the page context.
        Returns (ok, raw_text, length).
        """
        js = f"""
        (async () => {{
            try {{
                const resp = await fetch('{SAP_BASE}{endpoint}', {{
                    method: 'POST', credentials: 'include',
                    headers: {{'Content-Type': 'application/json; charset=utf-8', 'X-Requested-With': 'XMLHttpRequest'}},
                    body: JSON.stringify({json.dumps(payload)})
                }});
                const text = await resp.text();
                return JSON.stringify({{ok: resp.ok, text: text.substring(0, 500), len: text.length}});
            }} catch(e) {{ return JSON.stringify({{ok: false, error: e.message.substring(0, 200)}}); }}
        }})()
        """
        try:
            result_str = page.evaluate(js)
            result = json.loads(result_str)
            raw = result.get('text', '') or result.get('error', '')
            return result.get('ok', False), raw, result.get('len', 0)
        except Exception as e:
            return False, str(e)[:200], 0

    def is_real_data(self, text):
        """Check if response is actual JSON data (not an HTML error page)."""
        if '<!doctype' in text.lower() or 'SiteError' in text or '<html' in text.lower():
            return False
        if len(text) < 10:
            return False
        return True

    def extract_param(self, text):
        """Extract missing parameter name from SAP error message."""
        decoded = text.replace('\\u0027', "'")
        m = re.search(r"missing value for parameter:\s*'([^']+)'", decoded)
        return m.group(1) if m else None

    def try_endpoint(self, page, endpoint, payloads, TC=None):
        """
        Try an endpoint with multiple payload shapes.
        Handles param extraction automatically.
        Returns (cracked: bool, response: str, payload_used: dict)
        """
        tc = TC or self.TC
        for payload in payloads:
            # Replace None with TC in payload
            p = json.loads(json.dumps(payload).replace('null', f'"{tc}"')) if tc in json.dumps(payload) else payload
            ok, raw, length = self.fetch(page, endpoint, p)
            if ok and self.is_real_data(raw):
                # Check for missing param
                param = self.extract_param(raw)
                if param:
                    for val in [tc, 0, 1, "", {"CustomerID": tc},
                                {"Max": 5, "StartingRow": 0},
                                {"EntityID": tc, "EntityType": 1},
                                {"Year": 2026, "Month": 7, "Day": 1}]:
                        p2 = dict(p) if isinstance(p, dict) else {}
                        p2[param] = val
                        ok2, raw2, len2 = self.fetch(page, endpoint, p2)
                        if ok2 and self.is_real_data(raw2) and not self.extract_param(raw2):
                            return True, raw2, p2
                else:
                    return True, raw, p
            time.sleep(0.1)
        return False, "", {}

    def cracked(self, method, response_snippet, endpoint=None, payload=None):
        """Record a cracked endpoint."""
        ep = endpoint or method
        self.cracked_endpoints.append({
            'endpoint': ep,
            'method': method,
            'response': response_snippet,
            'payload': payload
        })
        self.log(f"  ✅ {method} → {response_snippet[:60]}")

    def failed(self, method, endpoint=None):
        """Record a failed endpoint."""
        ep = endpoint or method
        self.failed_endpoints.append({
            'endpoint': ep,
            'method': method
        })
        self.log(f"  ❌ {method}")

    def attach_request_listener(self, page):
        """Attach a global request listener to capture SPA-triggered API calls."""
        def on_request(request):
            url = request.url
            if any(x in url for x in ['/WebServices/', '/webservices/', '/CRMBFF/',
                                       '/AccountingBFF/', '/v3/WebServices/', '/api/']):
                path = url.replace(SAP_BASE, '') if SAP_BASE in url else url
                self.captured_requests.append({
                    'path': path,
                    'method': request.method,
                    'post_data': request.post_data,
                    'resource_type': request.resource_type,
                    'headers': {k: v for k, v in request.headers.items()
                               if k.lower() in ['content-type', 'x-requested-with']}
                })

        page.on('request', on_request)
        self._listener_attached = True

    def click_ui(self, page, selector, wait=2, description=None):
        """Click a UI element and wait for requests to fire."""
        try:
            el = page.query_selector(selector)
            if el:
                label = description or selector
                self.log(f"  Clicking: {label}")
                el.click(timeout=3000)
                time.sleep(wait)
                return True
        except:
            pass
        return False

    def navigate(self, page, path, wait=5, description=None):
        """Navigate to a SPA page and wait for requests."""
        url = f"{SAP_BASE}{path}" if path.startswith('/') else path
        label = description or path
        self.log(f"  Navigating to {label}...")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(wait)
            return True
        except:
            self.log(f"  Failed to navigate to {label}")
            return False

    def get_unique_captured(self):
        """Return unique captured request paths."""
        seen = set()
        unique = []
        for req in self.captured_requests:
            if req['path'] not in seen:
                seen.add(req['path'])
                unique.append(req)
        return unique

    def save_results(self):
        """Save all results to JSON file."""
        with open(self.results_file, 'w') as f:
            json.dump({
                'round': self.round_name,
                'captured_requests': self.captured_requests,
                'unique_captured': len(self.get_unique_captured()),
                'cracked_endpoints': self.cracked_endpoints,
                'failed_endpoints': self.failed_endpoints,
                'cracked_count': len(self.cracked_endpoints),
                'failed_count': len(self.failed_endpoints),
            }, f, indent=2, default=str)

    def summary(self):
        """Print and save final summary."""
        self.save_results()
        self.log(f"\n{'='*60}")
        self.log(f"R{self.round_name.upper()} SUMMARY:")
        self.log(f"  Total API requests captured from UI: {len(self.captured_requests)}")
        self.log(f"  Unique endpoints captured: {len(self.get_unique_captured())}")
        self.log(f"  Endpoints cracked: {len(self.cracked_endpoints)}")
        self.log(f"  Endpoints failed: {len(self.failed_endpoints)}")
        self.log(f"{'='*60}")


# Convenience: standard payload shapes to try for unknown endpoints
# None values get replaced with the test client GUID automatically
STANDARD_PAYLOADS = [
    {},
    {"Input": {}},
    {"InputData": {}},
    {"InputData": {"CustomerID": None}},
    {"InputData": {"EntityID": None, "EntityType": 1}},
    {"InputData": {"Max": 5, "StartingRow": 0}},
    {"Data": {"SearchString": ""}},
    {"request": {"CustomerID": None, "Start": 0, "Total": 25}},
    {"customerId": None},
    {"CustomerID": None},
]

PAYLOADS_CLIENT = [
    {"customerId": None},
    {"CustomerID": None},
    {"request": {"CustomerID": None, "Start": 0, "Total": 25, "ShowMore": False}},
    {"InputData": {"CustomerID": None}},
]

PAYLOADS_LIST = [
    {},
    {"Input": {}},
    {"InputData": {}},
    {"Data": {"SearchString": ""}},
    {"Type": 1},
]

PAYLOADS_ARTIFACT = [
    {"InputData": {"EntityID": None, "EntityType": 1, "Max": 5, "StartingRow": 0}},
    {"Input": {"EntityID": None, "EntityType": 1}},
    {"InputData": {"EntityID": None, "EntityType": 1}},
]
