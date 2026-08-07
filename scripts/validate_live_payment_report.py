#!/usr/bin/env python3
"""Immutable-base validator for KLD Payment Report publication pull requests.

The protected pull_request_target workflow runs this validator from main against
candidate files checked out separately. A pull request cannot weaken this code.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

CONTRACT_VERSION = "2026-08-07.1"
REQUIRED_PROVENANCE = {
    "contract_version": CONTRACT_VERSION,
    "refund_source": "verified_invoice_refund_lines",
    "prepay_classification": "invoice_prepayment_balance_display_only",
    "gst_source": "invoice_overlay_sales_tax",
    "cash_bridge": "gross_collected=applied_to_invoices+refunds_issued+currently_unused",
}
CENT = Decimal("0.01")


def money(value):
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_object(text: str, name: str):
    match = re.search(rf"const {re.escape(name)}\s*=\s*(\{{)", text)
    if not match:
        raise ValueError(f"HTML missing const {name}")
    start = match.start(1)
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:index + 1])
    raise ValueError(f"HTML has unclosed const {name}")


def validate(candidate: Path):
    data_path = candidate / "data" / "prepay_data.json"
    report_path = candidate / "prepay_report.html"
    nested_report = candidate / "reports" / "prepay_report.html"
    index_path = candidate / "index.html"
    manifest_path = candidate / "release_manifest.json"
    for path in (data_path, report_path, nested_report, index_path, manifest_path):
        if not path.is_file():
            raise ValueError(f"missing required release file {path.relative_to(candidate)}")

    if report_path.read_bytes() != nested_report.read_bytes() or report_path.read_bytes() != index_path.read_bytes():
        raise ValueError("index.html, prepay_report.html, and reports/prepay_report.html must be byte-identical")

    data = json.loads(data_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    for key in ("APPLIED", "DIRECT", "COLLECTED", "AUDIT"):
        if key not in data:
            raise ValueError(f"missing data key {key}")
    audit = data["AUDIT"]
    for key, expected in REQUIRED_PROVENANCE.items():
        if audit.get(key) != expected:
            raise ValueError(f"audit.{key} must be {expected!r}")
    if audit.get("detail_errors"):
        raise ValueError("invoice detail errors are present")

    applied, direct, collected = data["APPLIED"], data["DIRECT"], data["COLLECTED"]
    if list(applied) != list(direct) or list(applied) != list(collected):
        raise ValueError("month keys/order differ across report sections")

    count = sum(int(x.get("invoice_count", 0)) for x in applied.values()) + sum(int(x.get("invoice_count", 0)) for x in direct.values())
    revenue = money(sum((money(x.get("total")) for x in applied.values()), Decimal(0)) + sum((money(x.get("total")) for x in direct.values()), Decimal(0)))
    gst = money(sum((money(x.get("gst_total")) for x in applied.values()), Decimal(0)) + sum((money(x.get("gst_total")) for x in direct.values()), Decimal(0)))
    refunds = money(sum((abs(money(x.get("amount", x.get("absolute", 0)))) for x in audit.get("refund_rows") or []), Decimal(0)))
    credits = money(sum((abs(money(x.get("amount", x.get("absolute", 0)))) for x in audit.get("service_credit_rows") or []), Decimal(0)))

    if count != int(audit.get("invoice_count", -1)):
        raise ValueError("invoice count does not reconcile")
    if revenue != money(audit.get("combined_revenue")) or revenue != money(audit.get("sap_grand_total")):
        raise ValueError("combined revenue does not equal SAP control")
    if gst != money(audit.get("combined_gst")):
        raise ValueError("GST does not reconcile")
    if refunds != money(audit.get("refund_total")):
        raise ValueError("verified Refund invoice lines do not reconcile")
    if credits != money(audit.get("service_credit_total")):
        raise ValueError("service credits do not reconcile")

    bridge_refunds = Decimal(0)
    for month, row in collected.items():
        gross = money(row.get("prepayment_total"))
        applied_cash = money(row.get("applied_amount"))
        refund = money(row.get("refunds_issued"))
        unused = money(row.get("still_unused"))
        if gross != money(applied_cash + refund + unused):
            raise ValueError(f"{month} cash bridge fails")
        if money(row.get("net_collected")) != money(gross - refund):
            raise ValueError(f"{month} net collected fails")
        methods = row.get("by_method") or {}
        if sum(int(x.get("count", 0)) for x in methods.values()) != int(row.get("prepayment_count", -1)):
            raise ValueError(f"{month} payment method count fails")
        if money(sum((money(x.get("amount")) for x in methods.values()), Decimal(0))) != gross:
            raise ValueError(f"{month} payment method total fails")
        bridge_refunds += refund
    if money(bridge_refunds) != refunds:
        raise ValueError("cash-bridge refunds do not equal Refund invoice lines")

    html = report_path.read_text()
    for name, expected in (("APPLIED", applied), ("DIRECT", direct), ("COLLECTED", collected)):
        if extract_object(html, name) != expected:
            raise ValueError(f"HTML {name} data differs from data/prepay_data.json")
    for banned in ("SAP PaymentList refund total", "Prepay Applied"):
        if banned in html:
            raise ValueError(f"legacy/banned phrase present: {banned}")

    if manifest.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("release manifest contract version is wrong")
    artifacts = manifest.get("artifacts") or {}
    expected_files = {
        "data/prepay_data.json": data_path,
        "prepay_report.html": report_path,
        "index.html": index_path,
        "reports/prepay_report.html": nested_report,
    }
    for name, path in expected_files.items():
        record = artifacts.get(name) or {}
        if record.get("sha256") != sha(path) or record.get("size_bytes") != path.stat().st_size:
            raise ValueError(f"manifest checksum/size mismatch for {name}")
    controls = manifest.get("accounting_controls") or {}
    expected_controls = {
        "invoice_count": count,
        "combined_revenue": float(revenue),
        "combined_gst": float(gst),
        "refund_total": float(refunds),
        "service_credit_total": float(credits),
    }
    if controls != expected_controls:
        raise ValueError(f"manifest controls differ: {controls} != {expected_controls}")

    print(json.dumps({"status": "PASS", "contract_version": CONTRACT_VERSION, **expected_controls}, indent=2))


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    try:
        validate(root)
    except Exception as exc:
        print(f"LIVE PAYMENT REPORT CONTRACT FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
