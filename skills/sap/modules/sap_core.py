"""
sap_core.py — Base SAP HTTP Client
===================================
The foundation for all SAP API calls. Uses Option D cookie relay protocol.
All other modules import from this.

Usage:
  from sap.modules.sap_core import SAPClient
  sap = SAPClient()
  result = sap.post("/CRMBFF/CustomerSearch/SearchClientsLeads", {"SearchString": "John"})
"""
import json, os, sys, time, urllib.request, urllib.error

SAP_BASE = "https://my.serviceautopilot.com"
COOKIE_FILE = "/tmp/sap_cookies.json"
NULL_GUID = "00000000-0000-0000-0000-000000000000"
EMPTY_GUID = NULL_GUID

# KLD Company ID
COMPANY_ID = "ec7de8c0-3a71-4078-88e7-1a74e92c2415"

# KLD Division IDs
DIVISIONS = {
    "KLD": "697d8118-f9c9-4f60-aa69-cafbf81154e0",
    "MowSnow": "585804e7-d208-44c7-8901-cba0416c7c74",
    "BlueSpruce": "1161a81a-39d4-4540-9a0d-31a8abeb3577",
}

# Ethan's IDs (primary user)
USER_ID = "d94e4d73-3a62-4a2a-b4c8-5625cb8c19cc"
JOB_ID = "2488195c-7f46-4504-b7eb-f1ca7d37f17d"

class SAPClient:
    """Base SAP API client using cookie relay."""
    
    def __init__(self, cookie_file=COOKIE_FILE):
        self.cookie_file = cookie_file
        self._cookies = None
        self._cookie_str = None
        self._ua = None
        self._load_cookies()
    
    def _load_cookies(self):
        """Load cookies from file."""
        if not os.path.exists(self.cookie_file):
            raise RuntimeError(f"Cookie file not found: {self.cookie_file}. Run sap_auth.py first.")
        
        with open(self.cookie_file) as f:
            data = json.load(f)
        
        self._cookies = data
        # Build cookie string
        parts = []
        for c in data if isinstance(data, list) else data.get('cookies', []):
            name = c.get('name', '')
            value = c.get('value', '')
            if name and value:
                parts.append(f"{name}={value}")
            if c.get('name') == 'User-Agent' or not self._ua:
                if c.get('name') == 'User-Agent':
                    self._ua = c.get('value')
        
        self._cookie_str = "; ".join(parts)
        
        if not self._ua:
            self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
    
    def _make_request(self, path, body=None, method="POST", referer=None):
        """Make an HTTP request to SAP using cookie relay."""
        url = f"{SAP_BASE}{path}" if path.startswith("/") else f"{SAP_BASE}/{path}"
        
        if body is not None:
            data = json.dumps(body).encode('utf-8')
        else:
            data = b""
        
        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "Cookie": self._cookie_str,
            "User-Agent": self._ua,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": SAP_BASE,
            "Referer": f"{SAP_BASE}{referer}" if referer else f"{SAP_BASE}/Home.aspx",
        }
        
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read().decode('utf-8')
                # SAP .asmx endpoints wrap in {"d": ...}
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict) and "d" in parsed:
                        # Unwrap .asmx "d" wrapper
                        inner = parsed["d"]
                        if isinstance(inner, str):
                            try:
                                return json.loads(inner)
                            except:
                                return inner
                        return inner
                    return parsed
                except json.JSONDecodeError:
                    return content
        except urllib.error.HTTPError as e:
            body_text = ""
            try:
                body_text = e.read().decode('utf-8')[:200]
            except:
                pass
            raise RuntimeError(f"SAP API error {e.code} on {path}: {body_text}")
        except Exception as e:
            raise RuntimeError(f"Request failed for {path}: {str(e)}")
    
    def post(self, path, body=None):
        """POST to a SAP endpoint."""
        return self._make_request(path, body, "POST")
    
    
    def post_with_referer(self, path, body, referer):
        """POST with a specific Referer header (for context-gated endpoints)."""
        return self._make_request(path, body, "POST", referer=referer)

        """POST to a SAP endpoint."""
        return self._make_request(path, body, "POST")
    
    def get(self, path):
        """GET from a SAP endpoint."""
        return self._make_request(path, None, "GET")
    
    def unwrap(self, result, key=None, default=None):
        """Safely unwrap a SAP response."""
        if result is None:
            return default
        if isinstance(result, dict):
            if key:
                return result.get(key, default)
            # Common SAP response keys
            for k in ['Items', 'Results', 'Data', 'd', 'Accounts', 'Clients', 'Rows']:
                if k in result:
                    return result[k]
            return result
        if isinstance(result, list):
            return result
        return result
    
    def browser_date(self, year, month, day):
        """Create a SAP BrowserDate object."""
        return {"Year": year, "Month": month, "Day": day}
    
    def browser_date_from_str(self, date_str):
        """Create a BrowserDate from 'YYYY-MM-DD' string."""
        parts = date_str.split("-")
        return {"Year": int(parts[0]), "Month": int(parts[1]), "Day": int(parts[2])}


# Convenience singleton
_sap_instance = None

def get_sap():
    """Get or create a singleton SAPClient instance."""
    global _sap_instance
    if _sap_instance is None:
        _sap_instance = SAPClient()
    return _sap_instance
