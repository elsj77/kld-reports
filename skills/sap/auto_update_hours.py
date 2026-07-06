#!/usr/bin/env python3
"""
SAP Auto-Update Budgeted Hours — Data-driven service hour optimization.

Pulls ALL-TIME historical dispatch data for a client, groups by service code,
calculates recommended budgeted hours and crew size, and updates active
services in SAP. Preserves all notes, descriptions, and rates.

Usage:
    python3 auto_update_hours.py '<json_args>'

JSON args:
    {
        "address": "233 16th Ave S",        # required — client address
        "customer_id": "guid",              # optional — use instead of address
        "min_hours": 0.05,                  # optional — exclude visits ≤ this (default 0.05 = 3 min)
        "dry_run": false,                   # optional — just show recommendations, don't update
        "lookback_years": null,             # optional — limit lookback (default: all time)
        "aggressive": false                 # optional — use average instead of median
    }

Outputs: JSON with summary, per-service recommendations, and update results.
"""

import sys, json, re, os, statistics
from datetime import date, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules.sap_core import get_sap, USER_ID, JOB_ID, NULL_GUID
from modules.sap_dispatch import DispatchAPI
from modules.sap_service_update import ServiceUpdater, _clean_types, _fix_browser_date

# ============================================================
# SERVICE CODE MAPPING
# First keyword = primary identifier (weight 3 in matching)
# Remaining keywords = secondary confirmers (weight 1 each)
# A code must match its PRIMARY keyword to be considered.
# Among candidates, highest total score wins.
# ============================================================

SERVICE_KEYWORDS = {
    "CRAN/MOW":      ["mow", "lawn", "weekly"],
    "H/MOW":         ["hourly mow", "hourly", "h/mow"],
    "ELK/MOW":       ["elk", "mow"],
    "FW1":           ["round 1", "application", "fw round 1", "lawn spray"],
    "FW2":           ["round 2", "application", "fw round 2", "lawn spray"],
    "FW3":           ["round 3", "application", "fw round 3", "lawn spray"],
    "FW4":           ["round 4", "application", "fw round 4", "lawn spray"],
    "KICKSTART":     ["kick start", "kickstart"],
    "VGCTRL":        ["vegetation control", "veg control"],
    "VCFU":          ["veg control follow", "follow up", "follow-up", "vcfu"],
    "IRRIGATION/START": ["irrigation", "start-up", "startup", "start up", "start up"],
    "IRRIGATION/REP":   ["irrigation rep", "irrigation repair", "repair work"],
    "BLOW-OUT":      ["winterize", "blow out", "blowout", "blow-out", "blow"],
    "INSECTICIDE-1": ["insecticide-1", "insect control tree", "leaf miner"],
    "INSECTICIDE-2": ["insecticide-2", "insect control tree"],
    "INSECTICIDE-3": ["insecticide-3", "tent caterpillar", "tent"],
    "DORMA":         ["dormant oil", "dormant"],
    "FALL/GRAN/FERT": ["fall", "fertilizer", "granular", "gran"],
    "FALL/AERATE/GRANULAR": ["fall", "aerate", "aeration"],
    "SPRING/GRAN/FERT": ["spring", "fertilizer", "granular", "gran"],
    "SPRING/AERATE/GRANULAR": ["spring", "aerate", "aeration"],
    "SUMMER/GRAN/FERT": ["summer", "fertilizer", "granular"],
    "SE":            ["spring energizer", "spring cleanup", "cleanup"],
    "DEER":          ["deer", "repell", "repellant"],
    "INSTALL":       ["install", "installation"],
    "WASTE":         ["waste", "sweep", "clean up"],
}

CHEMICAL_CODES = {
    "SPRING/GRAN/FERT", "SPRING/AERATE/GRANULAR", "SUMMER/GRAN/FERT",
    "FALL/AERATE/GRANULAR", "FALL/GRAN/FERT", "ELK/MOW", "CRAN/MOW"
}


def filter_outliers(values, max_multiplier=3.0):
    """
    Remove outliers: any value > max_multiplier * median is excluded.
    E.g., a 26.8h mowing visit when median is 0.5h → 26.8 > 3*0.5=1.5 → excluded.
    """
    if len(values) < 4:
        return values  # Don't filter small samples
    med = statistics.median(values)
    threshold = med * max_multiplier
    filtered = [v for v in values if v <= threshold]
    if len(filtered) < 2:
        return values  # If filtering removes too much, keep original
    return filtered


def calculate_recommendation(hours_list, men_list, aggressive=False):
    """
    Calculate recommended hours and men from historical data.
    
    Strategy:
    - N >= 8: use median (robust against outliers)
    - N >= 4: use average
    - N >= 2: use average (flagged low confidence)
    - N == 1: use single value (flagged very low confidence)
    - N == 0: no recommendation
    """
    if not hours_list:
        return None, None, 0, "no_data"
    
    # Filter outliers first
    filtered = filter_outliers(hours_list)
    outliers_removed = len(hours_list) - len(filtered)
    
    n = len(filtered)
    
    if n >= 8:
        rec_h = statistics.median(filtered)
        confidence = "high"
    elif n >= 4:
        rec_h = sum(filtered) / n
        confidence = "medium"
    elif n >= 2:
        rec_h = sum(filtered) / n
        confidence = "low"
    else:
        rec_h = filtered[0]
        confidence = "very_low"
    
    if aggressive and n >= 2:
        rec_h = sum(filtered) / n
    
    rec_h = round(rec_h, 2)
    
    # Men: use median for small samples (robust), mode for large
    if men_list:
        if len(men_list) >= 8:
            men_counts = defaultdict(int)
            for m in men_list:
                men_counts[m] += 1
            rec_m = max(men_counts, key=men_counts.get)  # mode
        else:
            rec_m = int(round(statistics.median(men_list)))
            rec_m = max(1, rec_m)  # at least 1 person
    else:
        rec_m = None
    
    return rec_h, rec_m, n, confidence


def score_match(service_code, round_name, round_description=""):
    """
    Score how well a dispatch code matches a package round.
    Returns a numeric score (0 = no match, higher = better match).
    
    Primary keyword (first) gets weight 3. Secondary keywords get weight 1.
    Must match at least the primary keyword to get a non-zero score.
    """
    keywords = SERVICE_KEYWORDS.get(service_code, [])
    if not keywords:
        code_lower = service_code.lower()
        round_text = (round_name + " " + round_description).lower()
        return 3 if code_lower in round_text else 0
    
    round_text = re.sub(r'<[^>]+>', '', (round_name + " " + round_description).lower()).strip()
    
    # Check primary keyword (first in list) — must match
    primary = keywords[0]
    if primary not in round_text:
        return 0
    
    score = 3  # Primary matched
    for kw in keywords[1:]:
        if kw in round_text:
            score += 1
    
    return score


def find_best_match(service_code, round_name, round_description=""):
    """Check if a dispatch code matches a round. Returns True if best match."""
    score = score_match(service_code, round_name, round_description)
    return score > 0


def run(args):
    address = args.get("address", "")
    customer_id = args.get("customer_id", "")
    min_hours = args.get("min_hours", 0.05)  # 3 minutes — filters punch-in errors
    dry_run = args.get("dry_run", False)
    lookback_years = args.get("lookback_years")
    aggressive = args.get("aggressive", False)
    crew_recent_years = args.get("crew_recent_years", 3)  # Use recent data for crew size
    
    if not address and not customer_id:
        return {"error": "Either 'address' or 'customer_id' is required"}
    
    sap = get_sap()
    dispatch = DispatchAPI(sap)
    updater = ServiceUpdater(sap)
    
    today = date.today()
    if lookback_years:
        start = today - timedelta(days=365 * lookback_years)
    else:
        start = date(2010, 1, 1)  # All time
    
    # STEP 1: Pull all historical dispatch data
    query_params = {"start_date": start.isoformat(), "end_date": today.isoformat()}
    if address:
        query_params["address"] = address
    elif customer_id:
        query_params["customer_id"] = customer_id
    
    result = dispatch.query(**query_params)
    items = []
    if isinstance(result, dict):
        d = result.get("d", result)
        if isinstance(d, dict):
            items = d.get("ScheduledItems", d.get("Items", []))
    
    if not items:
        return {"error": f"No dispatch data found for {address or customer_id}"}
    
    if not customer_id and items:
        customer_id = items[0].get("CustomerID", "")
    
    # STEP 2: Filter and aggregate by (service_code, bh_bucket)
    # This handles clients with multiple services using the same code but different
    # budgeted hours (e.g., schools with trim crew BH=0.5 + field mow BH=4.0)
    excluded_count = 0
    service_stats = defaultdict(lambda: {
        "count": 0, "hours": [], "men": [], "men_dates": [], "budgeted": [],
        "completed": 0, "cancelled": 0, "excluded": 0, "bh_values": []
    })
    
    for item in items:
        service = item.get("Service", "")
        status = item.get("Status")
        men = int(item.get("NumberOfMen", 0) or 0)
        hours = float(item.get("Hours", 0) or 0)
        budgeted = float(item.get("BudgetedHours", 0) or 0)
        
        # Create BH bucket: round to nearest 0.5, treat 0 as its own bucket
        if budgeted > 0:
            bh_bucket = round(budgeted * 2) / 2
        else:
            bh_bucket = 0.0
        
        # Use composite key: service|bh_bucket
        # But only split if there are meaningful BH differences (>=1.0 apart)
        service_key = service  # default: group by service only
        
        stats = service_stats[service_key]
        stats["count"] += 1
        stats["bh_values"].append(budgeted)
        
        if status == 3:
            stats["completed"] += 1
            if hours > min_hours:
                stats["hours"].append(hours)
                if men > 0:
                    stats["men"].append(men)
                    stats["men_dates"].append(item.get("StartDate", ""))
                if budgeted > 0:
                    stats["budgeted"].append(budgeted)
            else:
                stats["excluded"] += 1
                excluded_count += 1
        elif status == 5:
            stats["cancelled"] += 1
    
    # Post-process: check if any service code has distinct BH clusters
    # If yes, split into separate groups for independent analysis
    # This handles schools with trim (BH=0.5) + field mow (BH=4.0) under same CRAN/MOW
    final_stats = {}
    for service_key, s in service_stats.items():
        bh_values = [v for v in s["bh_values"] if v > 0]
        if len(bh_values) >= 4:
            # Check for distinct clusters
            bh_set = set(round(v * 2) / 2 for v in bh_values)  # round to 0.5
            if len(bh_set) >= 2:
                # Find the gap — if there's a >=1.5h gap between clusters, split
                sorted_bh = sorted(bh_set)
                gaps = [(sorted_bh[i+1] - sorted_bh[i], sorted_bh[i], sorted_bh[i+1]) 
                       for i in range(len(sorted_bh)-1)]
                big_gaps = [g for g in gaps if g[0] >= 1.5]
                
                if big_gaps:
                    # Split into clusters based on the largest gap
                    big_gaps.sort(key=lambda x: -x[0])
                    split_point = (big_gaps[0][1] + big_gaps[0][2]) / 2
                    
                    # Re-process items for this service into two groups
                    low_items = [it for it in items 
                               if it.get("Service") == service_key 
                               and float(it.get("BudgetedHours", 0) or 0) <= split_point]
                    high_items = [it for it in items 
                                if it.get("Service") == service_key 
                                and float(it.get("BudgetedHours", 0) or 0) > split_point]
                    
                    if len(low_items) >= 2 and len(high_items) >= 2:
                        # Create two separate stat groups
                        for suffix, group_items, bh_label in [
                            (f"{service_key}|low", low_items, f"≤{split_point}"),
                            (f"{service_key}|high", high_items, f">{split_point}")
                        ]:
                            gs = {"count": 0, "hours": [], "men": [], "men_dates": [], 
                                  "budgeted": [], "completed": 0, "cancelled": 0, "excluded": 0,
                                  "bh_values": [], "bh_label": bh_label}
                            for item in group_items:
                                status = item.get("Status")
                                men = int(item.get("NumberOfMen", 0) or 0)
                                hours = float(item.get("Hours", 0) or 0)
                                budgeted = float(item.get("BudgetedHours", 0) or 0)
                                gs["count"] += 1
                                gs["bh_values"].append(budgeted)
                                if status == 3:
                                    gs["completed"] += 1
                                    if hours > min_hours:
                                        gs["hours"].append(hours)
                                        if men > 0:
                                            gs["men"].append(men)
                                            gs["men_dates"].append(item.get("StartDate", ""))
                                        if budgeted > 0:
                                            gs["budgeted"].append(budgeted)
                                    else:
                                        gs["excluded"] += 1
                                elif status == 5:
                                    gs["cancelled"] += 1
                            final_stats[suffix] = gs
                        continue  # Skip the default single-group path
        
        # No split needed — use original stats
        s["bh_label"] = "all"
        final_stats[service_key] = s
    
    service_stats = final_stats
    
    # STEP 3: Calculate recommendations per service code
    # For crew size: use only recent data (last crew_recent_years) to reflect current practices
    # For hours: use all-time data for maximum statistical power
    crew_cutoff = (today - timedelta(days=365 * crew_recent_years)).isoformat()
    
    recommendations = {}
    for code, s in service_stats.items():
        # Filter men list to recent visits only
        recent_men = []
        for i, m in enumerate(s["men"]):
            if i < len(s["men_dates"]) and s["men_dates"][i] >= crew_cutoff:
                recent_men.append(m)
        # Fall back to all-time men if no recent data
        men_for_calc = recent_men if len(recent_men) >= 1 else s["men"]
        
        rec_h, rec_m, n, confidence = calculate_recommendation(
            s["hours"], men_for_calc, aggressive
        )
        if rec_h is not None:
            # Calculate avg men for display
            avg_men = round(sum(s["men"]) / len(s["men"]), 1) if s["men"] else 0
            recommendations[code] = {
                "recommended_hours": rec_h,
                "recommended_men": rec_m,
                "data_points": n,
                "confidence": confidence,
                "bh_label": s.get("bh_label", "all"),
                "bh_median": round(statistics.median([v for v in s.get("bh_values", []) if v > 0]), 2) if [v for v in s.get("bh_values", []) if v > 0] else None,
                "excluded": s["excluded"],
                "avg_hours": round(sum(s["hours"]) / len(s["hours"]), 3) if s["hours"] else 0,
                "median_hours": round(statistics.median(s["hours"]), 3) if s["hours"] else 0,
                "min_hours": round(min(s["hours"]), 3) if s["hours"] else 0,
                "max_hours": round(max(s["hours"]), 3) if s["hours"] else 0,
                "avg_men": avg_men,
                "all_time_men_median": int(round(statistics.median(s["men"]))) if s["men"] else None,
                "recent_men_count": len(recent_men),
                "recent_men_values": recent_men,
                "crew_source": "recent" if len(recent_men) >= 1 else "all-time",
                "current_budgeted": round(sum(s["budgeted"]) / len(s["budgeted"]), 2) if s["budgeted"] else None,
            }
    
    # STEP 4: Load all active services for the client
    cust_result = sap.post("/WebServices/ClientViewWs.asmx/GetCustomerData", {"customerId": customer_id})
    cust_data = cust_result.get("d", cust_result) if isinstance(cust_result, dict) else cust_result
    if isinstance(cust_data, str):
        cust_data = json.loads(cust_data)
    customer_job_id = cust_data.get("Client", {}).get("CustomerJobID", NULL_GUID)
    
    services_result = sap.post("/WebServices/ClientViewWs.asmx/GetAllServicesAsync", {
        "request": {
            "CustomerID": customer_id,
            "AllJobs": True, "Start": 0, "Total": 100, "ShowMore": False,
            "CustomerJobID": customer_job_id,
            "IncludeCancelled": True, "GetAll": True
        }
    })
    svcs = services_result.get("d", services_result) if isinstance(services_result, dict) else services_result
    if isinstance(svcs, str):
        svcs = json.loads(svcs)
    all_jobs = svcs.get("Result", svcs).get("Jobs", [])
    active_jobs = [j for j in all_jobs if j.get("StateHelp") == "Running"]
    
    # STEP 5: Match service codes to active services and build update plan
    update_plan = []
    
    for job in active_jobs:
        job_id = job["ID"]
        job_name = job.get("Schedule", "")
        is_pkg = job.get("IsPackage", False)
        
        try:
            panel = sap.post("/WebServices/ServiceEditorWs.asmx/GetPanelData", {
                "Input": {"ServiceID": job_id, "Ticket": NULL_GUID}
            })
            pd = panel.get("d", panel) if isinstance(panel, dict) else panel
            if isinstance(pd, str):
                pd = json.loads(pd)
        except:
            continue
        
        panel_type = pd.get("__type", "")
        
        # Recurring service
        if "Recurring" in panel_type:
            details = pd.get("Service", {}).get("Details", [])
            for detail in details:
                svc_name = detail.get("ServiceName", "")
                current_h = detail.get("Hours", 0)
                current_m = detail.get("BudgetedNumberOfMen", 1)
                
                # Find best matching dispatch code
                # For multi-service clients (same code, different BH), use BH proximity
                best_code = None
                best_score = 0
                best_bh_diff = float('inf')
                for code in recommendations:
                    score = score_match(code, svc_name, detail.get("Description", ""))
                    if score == 0:
                        continue
                    # Check BH proximity — prefer recommendation groups with similar BH
                    rec_bh = recommendations[code].get("bh_median")
                    bh_diff = abs((rec_bh or 0) - (current_h or 0)) if rec_bh else 0
                    # Split codes (service|low/high) should match by BH proximity
                    if "|" in code:
                        code_base = code.split("|")[0]
                        if code_base not in svc_name.lower() and score < 3:
                            continue  # Skip split codes that don't match service name
                    
                    if (score > best_score or 
                        (score == best_score and bh_diff < best_bh_diff) or
                        (score == best_score and score > 0 and bh_diff == best_bh_diff and
                         recommendations[code]["data_points"] > recommendations.get(best_code, {}).get("data_points", 0))):
                        best_code = code
                        best_score = score
                        best_bh_diff = bh_diff
                
                if best_code:
                    rec = recommendations[best_code]
                    update_plan.append({
                        "job_id": job_id,
                        "job_name": job_name,
                        "service_type": "recurring",
                        "round_name": svc_name[:40],
                        "matched_code": best_code,
                        "match_score": best_score,
                        "current_hours": current_h,
                        "current_men": current_m,
                        "recommended_hours": rec["recommended_hours"],
                        "recommended_men": rec["recommended_men"],
                        "data_points": rec["data_points"],
                        "confidence": rec["confidence"],
                        "needs_update": (rec["recommended_hours"] != current_h or 
                                       (rec["recommended_men"] and rec["recommended_men"] != current_m)),
                    })
        
        # Package
        elif "Package" in panel_type:
            services = pd.get("Services", [])
            round_updates = []
            
            for i, svc in enumerate(services):
                svc_name = re.sub(r'<[^>]+>', '', svc.get("ServiceName", "")).strip()
                svc_desc = svc.get("Description", "")
                current_h = svc.get("Hours", 0)
                current_m = svc.get("BudgetedNumberOfMen", 1)
                is_active = svc.get("IsActive", True)
                
                # Find best matching dispatch code with BH proximity
                best_code = None
                best_score = 0
                best_bh_diff = float('inf')
                for code in recommendations:
                    score = score_match(code, svc_name, svc_desc)
                    if score == 0:
                        continue
                    rec_bh = recommendations[code].get("bh_median")
                    bh_diff = abs((rec_bh or 0) - (current_h or 0)) if rec_bh else 0
                    if "|" in code:
                        code_base = code.split("|")[0]
                        if code_base not in svc_name.lower() and score < 3:
                            continue
                    
                    if (score > best_score or 
                        (score == best_score and bh_diff < best_bh_diff) or
                        (score == best_score and score > 0 and bh_diff == best_bh_diff and
                         recommendations[code]["data_points"] > recommendations.get(best_code, {}).get("data_points", 0))):
                        best_code = code
                        best_score = score
                        best_bh_diff = bh_diff
                
                if best_code and is_active:
                    rec = recommendations[best_code]
                    round_updates.append({
                        "round_index": i,
                        "round_name": svc_name[:40],
                        "matched_code": best_code,
                        "match_score": best_score,
                        "current_hours": current_h,
                        "current_men": current_m,
                        "recommended_hours": rec["recommended_hours"],
                        "recommended_men": rec["recommended_men"],
                        "data_points": rec["data_points"],
                        "confidence": rec["confidence"],
                        "is_active": True,
                        "needs_update": (rec["recommended_hours"] != current_h or 
                                       (rec["recommended_men"] and rec["recommended_men"] != current_m)),
                    })
                elif best_code and not is_active:
                    rec = recommendations.get(best_code, {})
                    round_updates.append({
                        "round_index": i,
                        "round_name": svc_name[:40],
                        "matched_code": best_code,
                        "current_hours": current_h,
                        "current_men": current_m,
                        "recommended_hours": current_h,
                        "recommended_men": current_m,
                        "data_points": rec.get("data_points", 0),
                        "confidence": "inactive",
                        "is_active": False,
                        "needs_update": False,
                    })
                else:
                    round_updates.append({
                        "round_index": i,
                        "round_name": svc_name[:40],
                        "matched_code": None,
                        "current_hours": current_h,
                        "current_men": current_m,
                        "recommended_hours": current_h,
                        "recommended_men": current_m,
                        "data_points": 0,
                        "confidence": "no_match",
                        "is_active": is_active,
                        "needs_update": False,
                    })
            
            needs_update = any(r["needs_update"] for r in round_updates)
            update_plan.append({
                "job_id": job_id,
                "job_name": job_name,
                "service_type": "package",
                "rounds": round_updates,
                "needs_update": needs_update,
            })
    
    # Find unmatched dispatch codes
    matched_codes = set()
    for item in update_plan:
        if item["service_type"] == "recurring":
            if item.get("matched_code"):
                matched_codes.add(item["matched_code"])
                # Also mark the base code as matched
                if "|" in item["matched_code"]:
                    matched_codes.add(item["matched_code"].split("|")[0])
        elif item["service_type"] == "package":
            for r in item.get("rounds", []):
                if r.get("matched_code"):
                    matched_codes.add(r["matched_code"])
                    if "|" in r["matched_code"]:
                        matched_codes.add(r["matched_code"].split("|")[0])
    
    unmatched_dispatch = [code for code in recommendations if code not in matched_codes]
    
    # STEP 6: Execute updates
    results = []
    if not dry_run:
        for item in update_plan:
            if not item.get("needs_update"):
                continue
            
            job_id = item["job_id"]
            
            if item["service_type"] == "recurring":
                rec_h = item["recommended_hours"]
                rec_m = item["recommended_men"]
                
                result = updater.update_recurring(job_id, hours=rec_h, budgeted_men=rec_m)
                results.append({
                    "job": item["job_name"],
                    "type": "recurring",
                    "success": result["success"],
                    "errors": result["errors"],
                    "duplicate_ids": result.get("duplicate_ids", []),
                    "changes": result.get("changes", []),
                })
            
            elif item["service_type"] == "package":
                rounds = item["rounds"]
                active_rounds = [r for r in rounds if r.get("is_active") and r.get("needs_update")]
                if not active_rounds:
                    continue
                
                unique_hours = set(r["recommended_hours"] for r in active_rounds)
                unique_men = set(r["recommended_men"] for r in active_rounds)
                
                if len(unique_hours) == 1 and len(unique_men) == 1:
                    rec_h = list(unique_hours)[0]
                    rec_m = list(unique_men)[0]
                    result = updater.update_package(job_id, hours=rec_h, budgeted_men=rec_m)
                    results.append({
                        "job": item["job_name"],
                        "type": "package",
                        "success": result["success"],
                        "errors": result["errors"],
                        "duplicate_ids": result.get("duplicate_ids", []),
                        "changes": result.get("changes", []),
                    })
                else:
                    result = _update_package_per_round(sap, updater, job_id, rounds)
                    results.append({
                        "job": item["job_name"],
                        "type": "package_per_round",
                        "success": result["success"],
                        "errors": result["errors"],
                        "duplicate_ids": result.get("duplicate_ids", []),
                        "changes": result.get("changes", []),
                    })
    
    # STEP 7: Build summary
    total_visits = len(items)
    completed_visits = sum(s["completed"] for s in service_stats.values())
    real_visits = sum(len(s["hours"]) for s in service_stats.values())
    
    summary = {
        "address": address,
        "customer_id": customer_id,
        "lookback": f"{start.isoformat()} to {today.isoformat()}",
        "total_visits": total_visits,
        "completed_visits": completed_visits,
        "real_visits_used": real_visits,
        "excluded_visits": excluded_count,
        "min_hours_filter": min_hours,
        "active_services": len(active_jobs),
        "services_to_update": sum(1 for u in update_plan if u.get("needs_update")),
        "dry_run": dry_run,
        "crew_recent_years": crew_recent_years,
        "recommendations": recommendations,
        "update_plan": update_plan,
        "unmatched_dispatch_codes": unmatched_dispatch,
        "update_results": results,
    }
    
    return summary


def _update_package_per_round(sap, updater, service_id, rounds):
    """Custom package update where each round gets different hours."""
    d = updater._get_panel(service_id)
    customer_id = d.get("CustomerID", "")
    customer_job_id = updater._get_customer_job_id(customer_id)
    before_ids = updater._get_running_service_ids(customer_id, customer_job_id)
    
    panel_services = d.get("Services", [])
    save_services = []
    changes = []
    
    for i, svc in enumerate(panel_services):
        svc_id = svc.get("ServiceID", NULL_GUID)
        name_clean = re.sub(r'<[^>]+>', '', svc.get("ServiceName", "")).strip()
        old_h = svc.get("Hours")
        old_m = svc.get("BudgetedNumberOfMen")
        
        round_update = None
        for r in rounds:
            if r["round_index"] == i:
                round_update = r
                break
        
        if round_update and round_update.get("is_active") and round_update.get("needs_update"):
            new_h = round_update["recommended_hours"]
            new_m = round_update["recommended_men"]
        else:
            new_h = float(old_h or 0)
            new_m = int(old_m or 1)
        
        save_services.append({
            "ID": svc_id,
            "Description": svc.get("Description", name_clean),
            "Rate": float(svc.get("Rate", 0) or 0),
            "Quantity": float(svc.get("Quantity", 1) or 1),
            "Hours": new_h,
            "BudgetedNumberOfMen": new_m,
            "NumberOfDays": int(svc.get("NumberOfDays", 1) or 1),
            "AddToSchedule": svc.get("ShowAddToSchedule", False),
            "IsActive": svc.get("IsActive", True),
            "Products": svc.get("Products", []),
            "InstalledProducts": svc.get("InstalledProducts", []),
            "DiscountID": svc.get("DiscountID", NULL_GUID),
            "DiscountType": int(svc.get("DiscountType", 0) or 0),
            "DiscountAmount": float(svc.get("DiscountAmount", 0) or 0),
            "DiscountExpiration": {"Month": -1, "Day": -1, "Year": -1},
            "QuoteLineItemID": svc.get("QuoteLineItemID", NULL_GUID),
        })
        changes.append({
            "name": name_clean,
            "hours": (old_h, new_h),
            "men": (old_m, new_m),
            "rate": float(svc.get("Rate", 0) or 0),
        })
    
    save_payload = {"Input": {
        "UserID": USER_ID, "JobID": JOB_ID,
        "CustomerID": customer_id,
        "CustomerSourceID": d.get("CustomerSourceID", NULL_GUID),
        "ContractID": d.get("ContractID", NULL_GUID),
        "ServiceID": service_id,
        "PackageID": service_id,
        "SalesPersonID": d.get("SalesPersonID", NULL_GUID),
        "CSRID": d.get("CSRID", NULL_GUID),
        "InvoiceFreq": d.get("InvoiceFrequency", 1),
        "InvoiceAsWorkOrder": d.get("InvoiceAsWorkOrder", False),
        "PaymentType": d.get("PaymentType", 2),
        "CallAhead": d.get("CallAhead", False),
        "ArrivalWindow": d.get("ArrivalWindow", 0),
        "DontApplyMinimumAmount": d.get("DontApplyMinimumAmount", False),
        "UseAnnualPricing": d.get("UseAnnualPricing", False),
        "PONumber": d.get("PONumber", ""),
        "DateSold": _fix_browser_date(d.get("DateSold")),
        "WorkOrderNumber": d.get("WorkOrderNumber", ""),
        "AreaTreatedIDs": d.get("AreaTreatedIDs", []),
        "GroupJobs": d.get("GroupJobs", False),
        "GroupName": d.get("GroupName", ""),
        "IncludeSunday": d.get("IncludeSunday", True),
        "IncludeMonday": d.get("IncludeMonday", True),
        "IncludeTuesday": d.get("IncludeTuesday", True),
        "IncludeWednesday": d.get("IncludeWednesday", True),
        "IncludeThursday": d.get("IncludeThursday", True),
        "IncludeFriday": d.get("IncludeFriday", True),
        "IncludeSaturday": d.get("IncludeSaturday", True),
        "MaximumManHoursPerDay": d.get("MaximumManHoursPerDay", "9"),
        "CommissionOverrideData": {"CommissionIDs": [], "ResourceTypeIDs": [], "AmountList": []},
        "CommissionType": d.get("CommissionType", 0),
        "InternalNote": d.get("InternalNote", ""),
        "ShowInternalNoteRow": d.get("ShowInternalNoteRow", True),
        "SelectedPackageID": d.get("SelectedPackageID", NULL_GUID),
        "RenewalOption": d.get("RenewalOption", 2),
        "AssignedResourceIDs": d.get("AssignedResourceIDs", []),
        "RenewPackage": False,
        "ExcludeSunday": d.get("ExcludeSunday", False),
        "ExcludeMonday": d.get("ExcludeMonday", False),
        "ExcludeTuesday": d.get("ExcludeTuesday", False),
        "ExcludeWednesday": d.get("ExcludeWednesday", False),
        "ExcludeThursday": d.get("ExcludeThursday", False),
        "ExcludeFriday": d.get("ExcludeFriday", False),
        "ExcludeSaturday": d.get("ExcludeSaturday", False),
        "Services": save_services,
        "RouteSheetNotes": updater._preserve_route_sheet_notes(d.get("RouteSheetNotes", [])),
        "ServiceItems": {"Assets": []},
    }}
    
    result = sap.post("/WebServices/ServiceEditorWs.asmx/SavePackage", save_payload)
    d2 = updater._unwrap(result)
    errors = d2.get("Errors", [])
    dup_ids = updater._check_duplicates(customer_id, customer_job_id, before_ids) if not errors else set()
    
    return {
        "success": not errors and not dup_ids,
        "errors": errors,
        "changes": changes,
        "duplicate_ids": list(dup_ids),
    }


def _print_report(summary):
    """Print a human-readable report."""
    addr = summary.get("address", "")
    sep = "=" * 80
    print(f"\n{sep}")
    print(f"SAP AUTO-UPDATE BUDGETED HOURS — {addr}")
    print(f"Lookback: {summary['lookback']}")
    print(f"{sep}")
    print(f"\nTotal visits: {summary['total_visits']}")
    print(f"Completed visits: {summary['completed_visits']}")
    print(f"Real visits used (after filter): {summary['real_visits_used']}")
    print(f"Excluded (<={summary['min_hours_filter']}h / punch-in errors): {summary['excluded_visits']}")
    print(f"Active services: {summary['active_services']}")
    print(f"Services to update: {summary['services_to_update']}")
    print(f"Dry run: {summary['dry_run']}")
    
    print(f"\n{sep}")
    print("DISPATCH DATA ANALYSIS (All Time, Filtered + Outlier Removal)")
    print(f"{sep}")
    hdr = f"{'Service':25s} | {'N':>3s} | {'AvgHrs':>7s} | {'MedHrs':>7s} | {'MinHrs':>7s} | {'MaxHrs':>7s} | {'AvgMen':>6s} | {'RecHrs':>7s} | {'RecMen':>6s} | {'Conf':>10s} | {'CrewSrc':>8s}"
    print(f"\n{hdr}")
    print("-" * 155)
    
    for code in sorted(summary["recommendations"].keys()):
        r = summary["recommendations"][code]
        avg_m = r.get("avg_men", 0)
        rec_m = r["recommended_men"] or 0
        crew_src = r.get("crew_source", "?")
        all_time_m = r.get("all_time_men_median", "?")
        recent_vals = r.get("recent_men_values", [])
        print(f"{code:25s} | {r['data_points']:3d} | {r['avg_hours']:7.2f} | {r['median_hours']:7.2f} | {r['min_hours']:7.2f} | {r['max_hours']:7.2f} | {avg_m:6.1f} | {r['recommended_hours']:7.2f} | {rec_m:6d} | {r['confidence']:>10s} | {crew_src:>8s} | all-time:{all_time_m} recent:{recent_vals}")
    
    print(f"\n{sep}")
    print("UPDATE PLAN")
    print(f"{sep}")
    
    for item in summary["update_plan"]:
        if item["service_type"] == "recurring":
            status = "UPDATE" if item.get("needs_update") else "OK"
            print(f"\n  [{status}] {item['job_name']} (Recurring)")
            print(f"       Round: {item['round_name']}")
            cur_h = item['current_hours']
            cur_m = item['current_men']
            rec_h = item['recommended_hours']
            rec_m = item['recommended_men']
            print(f"       {cur_h}h/{cur_m}m -> {rec_h}h/{rec_m}m")
            print(f"       Matched: {item['matched_code']} (score={item.get('match_score',0)}, {item['data_points']} pts, {item['confidence']})")
        elif item["service_type"] == "package":
            status = "UPDATE" if item.get("needs_update") else "OK"
            print(f"\n  [{status}] {item['job_name']} (Package)")
            for r in item.get("rounds", []):
                conf = r.get("confidence", "?")
                if conf == "no_match":
                    print(f"       Round {r['round_index']}: {r['round_name']} -- NO MATCH (kept as-is)")
                elif conf == "inactive":
                    print(f"       Round {r['round_index']}: {r['round_name']} -- INACTIVE (kept as-is)")
                else:
                    arrow = "->" if r.get("needs_update") else "="
                    cur_h = r['current_hours']
                    cur_m = r['current_men']
                    rec_h = r['recommended_hours']
                    rec_m = r['recommended_men']
                    mc = r.get('matched_code', '?')
                    dp = r.get('data_points', 0)
                    print(f"       Round {r['round_index']}: {r['round_name']} | {cur_h}h/{cur_m}m {arrow} {rec_h}h/{rec_m}m | {mc} ({dp} pts, {conf})")
    
    if summary.get("unmatched_dispatch_codes"):
        print(f"\n{sep}")
        print("UNMATCHED DISPATCH CODES (no active service found)")
        print(f"{sep}")
        for code in summary["unmatched_dispatch_codes"]:
            r = summary["recommendations"][code]
            print(f"  {code:25s} | {r['data_points']} pts | {r['recommended_hours']}h/{r['recommended_men']}m")
    
    if summary.get("update_results"):
        print(f"\n{sep}")
        print("UPDATE RESULTS")
        print(f"{sep}")
        for r in summary["update_results"]:
            print(f"\n  {r['job']} ({r['type']})")
            print(f"    Success: {r['success']}")
            if r["errors"]:
                print(f"    Errors: {r['errors']}")
            if r.get("duplicate_ids"):
                print(f"    Duplicates cancelled: {r['duplicate_ids']}")
            for c in r.get("changes", []):
                old_h = c['hours'][0]
                new_h = c['hours'][1]
                old_m = c['men'][0]
                new_m = c['men'][1]
                print(f"    {c['name'][:35]:35s} | {old_h}h -> {new_h}h | {old_m}m -> {new_m}m")


if __name__ == "__main__":
    args = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    summary = run(args)
    if "error" in summary:
        print(f"ERROR: {summary['error']}")
        sys.exit(1)
    _print_report(summary)
    print("\nJSON_RESULT:" + json.dumps(summary, default=str))
