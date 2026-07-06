#!/usr/bin/env python3
"""
sync_pp_to_sheets.py
--------------------
Pulls SAP timesheets for a pay period and writes them to the PP Google Sheet.

Usage:
  python3 sync_pp_to_sheets.py [--pp N]   # explicit PP number
  python3 sync_pp_to_sheets.py             # auto-detect current/most recent PP

Requires env vars:
  GOOGLEDOCS_ACCESS_TOKEN  — from Base44 googledocs connector
  SAP_SESSION_COOKIE       — c6577811 session (from OAuthToken entity)
  SAP_ACCOUNT_NUMBER       — e.g. c6577811

Output:
  Writes W1 hours, W2 hours, Reg, OT, Total to the correct PP tab.
  Removes employees absent from SAP timesheets (deactivated/not present).
  Appends new employees not yet in the sheet.
"""

import os, sys, json, datetime, argparse, subprocess

for pkg in ['requests']:
    try: __import__(pkg)
    except ImportError: subprocess.check_call([sys.executable,'-m','pip','install',pkg,'-q'])

import requests

# ── Constants ────────────────────────────────────────────────────────────────
GREEN_BORDER = {
    "style": "SOLID", "width": 1,
    "color": {"red": 0.50980395, "green": 0.7764706, "blue": 0.5176471},
    "colorStyle": {"rgbColor": {"red": 0.50980395, "green": 0.7764706, "blue": 0.5176471}}
}
CELL_FORMAT = {
    "borders": {
        "top": GREEN_BORDER, "bottom": GREEN_BORDER,
        "left": GREEN_BORDER, "right": GREEN_BORDER
    },
    "textFormat": {"fontFamily": "Roboto"}
}

PP1_START   = datetime.date(2025, 11, 9)
PP_LENGTH   = 14
SHEET_ID    = "16P14G-So3m8gjKcprm8rDtcqeqnlqPs-bsIYYBQfEBk"
SAP_BASE    = "https://my.serviceautopilot.com"
ACCOUNT_NUM = os.environ.get("SAP_ACCOUNT_NUMBER", "c6577811")

SALARY_NAMES = {
    'Phil Budiselich', 'Brett Mason', 'Ethan St. Jean',
    'Cam St. Jean', 'Cam Mertz', 'Marcie St. Jean', 'Kyle Wood',
}

# Employees permanently excluded from the sheet (never synced regardless of hours)
EXCLUDE_NAMES = {
    'Paul Visentin',
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def pp_dates(pp_num: int):
    start  = PP1_START + datetime.timedelta(days=(pp_num - 1) * PP_LENGTH)
    end    = start + datetime.timedelta(days=PP_LENGTH - 1)
    w1_end = start + datetime.timedelta(days=6)
    return start, end, w1_end

def detect_current_pp() -> int:
    today = datetime.date.today()
    delta = (today - PP1_START).days
    pp    = delta // PP_LENGTH + 1
    start, end, _ = pp_dates(pp)
    # If today is on or after end date, that PP is done — use it
    # If still in progress, use previous completed one
    return pp if today >= end else pp - 1

def sheet_tab_name(pp_num: int, start: datetime.date, end: datetime.date) -> str:
    mo = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    s, e = mo[start.month-1], mo[end.month-1]
    if start.month == end.month:
        return f"PP{pp_num} \u2014 {s} {start.day} to {end.day}"
    return f"PP{pp_num} \u2014 {s} {start.day} to {e} {end.day}"

def get_sap_cookie() -> str:
    """Load SAP session cookie from OAuthToken entity or env."""
    cookie = os.environ.get("SAP_SESSION_COOKIE", "")
    if cookie:
        return cookie
    # Try loading from Base44 entity via simple file cache
    cache = "/tmp/sap_session_cookie.txt"
    if os.path.exists(cache):
        return open(cache).read().strip()
    raise RuntimeError("SAP_SESSION_COOKIE not set. Run sap_auth.py first.")

def pull_sap_hours(pp_num: int, cookie: str) -> list[dict]:
    """Pull timesheet data from SAP for a pay period. Returns list of employee records."""
    start, end, w1_end = pp_dates(pp_num)
    w2_start = w1_end + datetime.timedelta(days=1)

    def fmt(d): return d.strftime("%Y-%m-%d")

    headers = {
        "Cookie": cookie,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    }

    def fetch_ts(date_from: str, date_to: str) -> list[dict]:
        payload = {
            "request": {
                "DateFrom": date_from,
                "DateTo":   date_to,
                "IncludeAllEmployees": True,
            }
        }
        url = f"{SAP_BASE}/Services/Mobile/v3/TimeTracking/GetTimesheetEntries"
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        return data.get("TimesheetEntries") or data.get("Data") or []

    w1_entries = fetch_ts(fmt(start),    fmt(w1_end))
    w2_entries = fetch_ts(fmt(w2_start), fmt(end))

    def sum_hours(entries: list) -> dict[str, float]:
        totals: dict[str, float] = {}
        for e in entries:
            name = (e.get("EmployeeName") or "").strip()
            hrs  = float(e.get("Hours") or e.get("TotalHours") or 0)
            if name:
                totals[name] = round(totals.get(name, 0) + hrs, 2)
        return totals

    w1 = sum_hours(w1_entries)
    w2 = sum_hours(w2_entries)
    all_names = sorted(set(list(w1.keys()) + list(w2.keys())))

    results = []
    for name in all_names:
        if name in EXCLUDE_NAMES:
            continue  # Permanently excluded from sheet
        h1    = w1.get(name, 0)
        h2    = w2.get(name, 0)
        total = round(h1 + h2, 2)
        reg   = min(total, 80.0) if name not in SALARY_NAMES else None
        ot    = round(total - 80.0, 2) if (name not in SALARY_NAMES and total > 80) else None
        results.append({
            "name": name,
            "w1": h1 or None,
            "w2": h2 or None,
            "total_reg": reg,
            "total_ot":  ot if ot and ot > 0 else None,
        })

    return results

# ── Sheets helpers ────────────────────────────────────────────────────────────

def sheets_get(token: str, range_: str) -> list[list]:
    import urllib.parse
    enc = urllib.parse.quote(range_)
    r = requests.get(
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{enc}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15
    )
    r.raise_for_status()
    return r.json().get("values", [])

def sheets_batch_update(token: str, data: list[dict]):
    r = requests.post(
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values:batchUpdate",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"valueInputOption": "USER_ENTERED", "data": data},
        timeout=15
    )
    r.raise_for_status()
    return r.json()

def sheets_delete_rows(token: str, sheet_id: int, row_indices: list[int]):
    """Delete rows (0-indexed, sorted descending) from the sheet."""
    requests_list = []
    for idx in sorted(row_indices, reverse=True):
        requests_list.append({"deleteDimension": {"range": {
            "sheetId": sheet_id, "dimension": "ROWS",
            "startIndex": idx, "endIndex": idx + 1
        }}})
    r = requests.post(
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}:batchUpdate",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"requests": requests_list},
        timeout=15
    )
    r.raise_for_status()

def sheets_append_rows(token: str, tab: str, rows: list[list]):
    import urllib.parse
    enc = urllib.parse.quote(f"{tab}!A:H")
    r = requests.post(
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{enc}:append",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
        json={"values": rows},
        timeout=15
    )
    r.raise_for_status()
    return r.json()

def get_sheet_numeric_id(token: str, tab_title: str) -> int:
    r = requests.get(
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}?fields=sheets.properties",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15
    )
    r.raise_for_status()
    for s in r.json()["sheets"]:
        if s["properties"]["title"] == tab_title:
            return s["properties"]["sheetId"]
    raise ValueError(f"Tab '{tab_title}' not found in spreadsheet")

# ── Main sync logic ───────────────────────────────────────────────────────────

def sync_pp(pp_num: int, token: str, cookie: str):
    start, end, _ = pp_dates(pp_num)
    tab = sheet_tab_name(pp_num, start, end)
    print(f"Syncing PP{pp_num}: {start} → {end} | Tab: '{tab}'")

    # 1. Pull SAP hours
    sap_results = pull_sap_hours(pp_num, cookie)
    sap_by_name = {r["name"]: r for r in sap_results}
    sap_names_lower = {n.lower() for n in sap_by_name}
    print(f"  SAP: {len(sap_results)} employees with timesheet data")

    # 2. Read current sheet rows (header in row 6, data from row 7)
    sheet_numeric_id = get_sheet_numeric_id(token, tab)
    current_rows = sheets_get(token, f"{tab}!A6:H60")
    # current_rows[0] = header, [1..] = employee rows
    header     = current_rows[0] if current_rows else []
    emp_rows   = current_rows[1:]  # 0-indexed within emp_rows, sheet row = i+7

    # 3. Identify rows to delete (sheet employees not in SAP timesheets this period)
    rows_to_delete_0idx = []  # 0-indexed in full sheet (row 6 = index 5, row 7 = index 6)
    rows_to_update      = []  # (sheet_row_1idx, emp_data)
    sheet_emp_names     = set()

    for i, row in enumerate(emp_rows):
        first = row[0].strip() if len(row) > 0 else ""
        last  = row[1].strip() if len(row) > 1 else ""
        if not first and not last:
            continue
        full_name  = f"{first} {last}"
        full_lower = full_name.lower()
        sheet_emp_names.add(full_lower)

        # Check if this employee appears in SAP this period
        matched_sap_name = None
        for sap_name in sap_by_name:
            if sap_name.lower() == full_lower:
                matched_sap_name = sap_name
                break
            # Handle "Cam Mertz" → "Cam St. Jean" alias
            if full_lower == "cam mertz" and sap_name.lower() == "cam st. jean":
                matched_sap_name = sap_name
                break

        if matched_sap_name is None:
            # Not in SAP timesheets — mark for deletion
            sheet_row_0idx = i + 6  # row 7 = index 6 (0-based), so emp_row[0] = sheet row 7 = 0-index 6
            rows_to_delete_0idx.append(sheet_row_0idx)
            print(f"  REMOVE: {full_name} (not in SAP timesheets)")
        else:
            rows_to_update.append((i + 7, matched_sap_name))  # sheet row 1-indexed

    # 4. Delete inactive rows (bottom-up to preserve indices)
    if rows_to_delete_0idx:
        sheets_delete_rows(token, sheet_numeric_id, rows_to_delete_0idx)
        print(f"  Deleted {len(rows_to_delete_0idx)} inactive rows")

    # 5. Re-read sheet after deletions to get correct row numbers
    current_rows2 = sheets_get(token, f"{tab}!A6:H60")
    emp_rows2 = current_rows2[1:]

    # 6. Write hours for existing employees
    value_ranges = []
    for i, row in enumerate(emp_rows2):
        first = row[0].strip() if len(row) > 0 else ""
        last  = row[1].strip() if len(row) > 1 else ""
        if not first and not last:
            continue
        full_lower = f"{first} {last}".lower()
        sheet_row  = i + 7  # 1-indexed

        matched = None
        for sap_name in sap_by_name:
            if sap_name.lower() == full_lower:
                matched = sap_name
                break
            if full_lower == "cam mertz" and sap_name.lower() == "cam st. jean":
                matched = sap_name
                break

        if not matched:
            continue

        emp     = sap_by_name[matched]
        is_sal  = matched in SALARY_NAMES
        w1      = emp["w1"] or ""
        w2      = emp["w2"] or ""
        reg     = emp["total_reg"] if emp["total_reg"] else ""
        ot      = emp["total_ot"]  if emp["total_ot"]  else ""
        tot     = "Salary" if is_sal else round((emp["total_reg"] or 0) + (emp["total_ot"] or 0), 2)

        value_ranges.append({"range": f"'{tab}'!C{sheet_row}:F{sheet_row}", "values": [[w1, w2, reg, ot]]})
        value_ranges.append({"range": f"'{tab}'!H{sheet_row}",              "values": [[tot]]})

    if value_ranges:
        result = sheets_batch_update(token, value_ranges)
        print(f"  Updated {result.get('totalUpdatedCells',0)} cells for existing employees")

    # 7. Append new employees (in SAP but not in sheet)
    existing_lower = {f"{r[0].strip()} {r[1].strip()}".lower() for r in emp_rows2 if r}
    existing_lower.add("cam st. jean")  # alias for cam mertz

    new_rows = []
    for emp in sorted(sap_results, key=lambda x: x["name"].split()[-1].lower()):
        name_lower = emp["name"].lower()
        if name_lower in existing_lower:
            continue
        parts  = emp["name"].split()
        first  = parts[0]
        last   = " ".join(parts[1:])
        is_sal = emp["name"] in SALARY_NAMES
        w1     = emp["w1"] or ""
        w2     = emp["w2"] or ""
        reg    = emp["total_reg"] if emp["total_reg"] else ""
        ot     = emp["total_ot"]  if emp["total_ot"]  else ""
        tot    = "Salary" if is_sal else round((emp["total_reg"] or 0) + (emp["total_ot"] or 0), 2)
        new_rows.append([first, last, w1, w2, reg, ot, "", tot])
        print(f"  APPEND: {emp['name']} → Total={tot}")

    if new_rows:
        sheets_append_rows(token, tab, new_rows)
        print(f"  Appended {len(new_rows)} new employee rows")

    # 8. Apply consistent border formatting to ALL employee rows (7 → last row)
    #    This ensures appended rows and any rows that survived deletion all look the same.
    current_after = sheets_get(token, f"{tab}!A6:A60")
    last_emp_row = 6
    for i, row in enumerate(current_after[1:], start=1):  # skip header at index 0
        val = row[0].strip() if row else ""
        if val:
            last_emp_row = 6 + i

    if last_emp_row > 6:
        fmt_requests = []
        for sheet_row in range(7, last_emp_row + 1):
            fmt_requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId":          sheet_numeric_id,
                        "startRowIndex":    sheet_row - 1,
                        "endRowIndex":      sheet_row,
                        "startColumnIndex": 0,
                        "endColumnIndex":   9
                    },
                    "cell": {"userEnteredFormat": CELL_FORMAT},
                    "fields": "userEnteredFormat.borders,userEnteredFormat.textFormat.fontFamily"
                }
            })
        fmt_resp = requests.post(
            f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}:batchUpdate",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"requests": fmt_requests},
            timeout=30
        )
        fmt_resp.raise_for_status()
        print(f"  Formatting applied to rows 7–{last_emp_row}")

    print(f"✅ PP{pp_num} sync complete.")
    return {"pp": pp_num, "tab": tab, "updated": len(value_ranges)//2, "appended": len(new_rows), "removed": len(rows_to_delete_0idx)}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pp", type=int, default=None, help="Pay period number (default: auto-detect)")
    args = parser.parse_args()

    token  = os.environ.get("GOOGLEDOCS_ACCESS_TOKEN", "")
    cookie = get_sap_cookie()

    if not token:
        print("ERROR: GOOGLEDOCS_ACCESS_TOKEN not set")
        sys.exit(1)

    pp_num = args.pp or detect_current_pp()
    result = sync_pp(pp_num, token, cookie)
    print(json.dumps(result))
