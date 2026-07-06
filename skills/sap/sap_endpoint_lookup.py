#!/usr/bin/env python3
"""
SAP Endpoint Lookup — Search the SAP API map for endpoints, payloads, and auth patterns.
Usage:
  python3 sap_endpoint_lookup.py <search terms>          # Search for endpoints
  python3 sap_endpoint_lookup.py --preflight <task>       # Pre-flight check before SAP work
  python3 sap_endpoint_lookup.py --rebuild                # Rebuild the index from API map
  python3 sap_endpoint_lookup.py --list-sections          # List all sections in the map

The index is cached at /tmp/sap_endpoint_index.json for fast lookups.
Rebuild after updating sap_api_map.md.

Exit codes: 0=found results, 1=no results, 2=index needs rebuild
"""
import json, os, re, sys, subprocess
from pathlib import Path

API_MAP = '/app/.agents/rules/sap_api_map.md'
INDEX_CACHE = '/tmp/sap_endpoint_index.json'

def log(m):
    print(f"[SAP-LOOKUP] {m}", file=sys.stderr)

def parse_api_map():
    """Parse sap_api_map.md into structured endpoint index."""
    with open(API_MAP, 'r') as f:
        lines = f.readlines()
    
    endpoints = []
    sections = []
    current_section = "Unknown"
    current_auth_tier = ""
    
    # Patterns to match endpoints
    # Table rows: | `EndpointPath` | wrapper | payload | notes |
    table_re = re.compile(r'^\|\s*`?([^|`]+\.asmx/[^|`]+|[^|`]+/BFF/[^|`]+|[^|`]+/v3/[^|`]+)`?\s*\|')
    # Inline endpoints: `EndpointPath` or Endpoint paths in code blocks
    inline_re = re.compile(r'`([^`]+\.asmx/[A-Za-z_]+|[^`]+/BFF/[A-Za-z_/]+|[^`]+/v3/[A-Za-z_/]+)`')
    # Section headers
    section_re = re.compile(r'^##+\s+(.+)')
    # Auth tier mentions
    tier_re = re.compile(r'(Tier [123]|SPA.context|page.evaluate|cookie.session|Tier 2 OK|NOT Tier 2)', re.IGNORECASE)
    
    for i, line in enumerate(lines):
        # Track sections
        m = section_re.match(line)
        if m:
            current_section = m.group(1).strip()
            sections.append(current_section)
            continue
        
        # Track auth tier mentions in current context
        tm = tier_re.search(line)
        if tm:
            current_auth_tier = tm.group(1)
        
        # Parse table rows
        m = table_re.match(line)
        if m:
            path = m.group(1).strip().strip('`')
            # Parse remaining columns
            parts = line.split('|')
            if len(parts) >= 4:
                wrapper = parts[2].strip().strip('`').strip()
                payload = parts[3].strip().strip('`').strip() if len(parts) > 3 else ''
                notes = parts[4].strip().strip('`').strip() if len(parts) > 4 else ''
                
                # Clean up payload (remove markdown formatting)
                payload = payload.replace('`', '').strip()
                notes = notes.replace('`', '').strip()
                
                # Detect auth tier from notes and surrounding context
                auth = 'Tier 2 OK'
                combined = (notes + ' ' + line + ' ' + current_auth_tier).lower()
                if 'spa context' in combined or 'not tier 2' in combined or 'spa-only' in combined:
                    auth = 'SPA context (Tier 1/3 only)'
                elif 'page.evaluate' in combined:
                    auth = 'Tier 3 (page.evaluate)'
                elif 'tier 1' in combined:
                    auth = 'Tier 1 (Browserbase)'
                elif 'bare' in combined and wrapper in ('—', '-', 'bare', ''):
                    auth = 'Tier 2 OK (bare call)'
                
                endpoints.append({
                    'path': path,
                    'wrapper': wrapper,
                    'payload': payload[:500],
                    'notes': notes[:300],
                    'section': current_section,
                    'auth': auth,
                    'line': i + 1
                })
            continue
        
        # Parse inline endpoints in code blocks or text
        for m in inline_re.finditer(line):
            path = m.group(1).strip()
            # Skip if already captured in a table
            if not any(e['path'] == path for e in endpoints):
                # Get surrounding context
                context = ''
                if i > 0:
                    context = lines[i-1].strip()[:100]
                if i < len(lines) - 1:
                    context += ' ' + lines[i+1].strip()[:100]
                
                # Detect wrapper from the line
                wrapper = ''
                wm = re.search(r'(?:wrapper|Wrapper)[:\s]+(\w+)', line)
                if wm:
                    wrapper = wm.group(1)
                
                # Detect auth tier
                auth = 'Tier 2 OK'
                combined = (line + ' ' + context + ' ' + current_auth_tier).lower()
                if 'spa context' in combined or 'not tier 2' in combined or 'spa-only' in combined:
                    auth = 'SPA context (Tier 1/3 only)'
                elif 'page.evaluate' in combined:
                    auth = 'Tier 3 (page.evaluate)'
                elif 'tier 1' in combined or 'browserbase' in combined:
                    auth = 'Tier 1 (Browserbase)'
                
                # Extract payload if on same line
                payload = ''
                pm = re.search(r'(?:payload|body|Payload)[:\s]+(\{[^}]+\})', line)
                if pm:
                    payload = pm.group(1)[:500]
                
                endpoints.append({
                    'path': path,
                    'wrapper': wrapper,
                    'payload': payload,
                    'notes': line.strip()[:200],
                    'section': current_section,
                    'auth': auth,
                    'line': i + 1
                })
    
    return endpoints, sections

def build_index():
    """Build and cache the endpoint index."""
    log(f"Parsing {API_MAP}...")
    endpoints, sections = parse_api_map()
    
    index = {
        'generated_at': __import__('datetime').datetime.now().isoformat(),
        'total_endpoints': len(endpoints),
        'total_sections': len(sections),
        'sections': sections,
        'endpoints': endpoints
    }
    
    with open(INDEX_CACHE, 'w') as f:
        json.dump(index, f, indent=2)
    
    log(f"Index built: {len(endpoints)} endpoints across {len(sections)} sections")
    return index

def load_index():
    """Load the cached index, or rebuild if missing/stale."""
    if not os.path.exists(INDEX_CACHE):
        log("Index cache not found, building...")
        return build_index()
    
    # Check if API map is newer than cache
    map_mtime = os.path.getmtime(API_MAP)
    cache_mtime = os.path.getmtime(INDEX_CACHE)
    
    if map_mtime > cache_mtime:
        log("API map updated since last index build, rebuilding...")
        return build_index()
    
    with open(INDEX_CACHE, 'r') as f:
        return json.load(f)

def search(query, index):
    """Search the index for endpoints matching the query."""
    query = query.lower().strip()
    terms = query.split()
    
    results = []
    for ep in index['endpoints']:
        score = 0
        haystack = (ep['path'] + ' ' + ep['notes'] + ' ' + ep['section'] + ' ' + ep['wrapper']).lower()
        
        for term in terms:
            if term in ep['path'].lower():
                score += 10  # Path match is highest priority
            if term in haystack:
                score += 3
            if term in ep['section'].lower():
                score += 2
            if term in ep['notes'].lower():
                score += 1
        
        if score > 0:
            results.append({**ep, 'score': score})
    
    # Sort by score descending, then by path
    results.sort(key=lambda x: (-x['score'], x['path']))
    return results

def format_result(ep):
    """Format a single endpoint for display."""
    lines = []
    lines.append(f"  📡 {ep['path']}")
    if ep.get('wrapper') and ep['wrapper'] not in ('—', '-', '', 'bare'):
        lines.append(f"     Wrapper: {ep['wrapper']}")
    if ep.get('payload'):
        # Truncate long payloads
        payload = ep['payload']
        if len(payload) > 200:
            payload = payload[:200] + '...'
        lines.append(f"     Payload: {payload}")
    lines.append(f"     Auth: {ep.get('auth', 'Tier 2 OK')}")
    if ep.get('notes'):
        notes = ep['notes']
        if len(notes) > 150:
            notes = notes[:150] + '...'
        lines.append(f"     Notes: {notes}")
    lines.append(f"     Section: {ep.get('section', '?')} (line {ep.get('line', '?')})")
    return '\n'.join(lines)

def preflight(task):
    """Pre-flight check before SAP work. Returns auth requirements and relevant endpoints."""
    print("=" * 70)
    print("SAP PRE-FLIGHT CHECK")
    print("=" * 70)
    
    # Load auth pattern
    auth_file = '/app/.agents/rules/sap_auth_pattern.md'
    if os.path.exists(auth_file):
        with open(auth_file, 'r') as f:
            auth_content = f.read()[:500]
        print("\n📋 AUTH PATTERN (sap_auth_pattern.md):")
        print("  Tier 1: Browserbase + build_js_call() (interactive)")
        print("  Tier 2: sap_auth.get_sap_session() (sandbox cookie relay)")
        print("  Tier 3: Playwright + page.evaluate() (GitHub Actions)")
        print("  ⚠️  NEVER use raw requests.Session() — Incapsula blocks it")
    
    # Check cookie freshness
    cookie_file = '/tmp/sap_cookies.json'
    if os.path.exists(cookie_file):
        import time
        age = time.time() - os.path.getmtime(cookie_file)
        age_min = int(age / 60)
        age_hrs = age_min / 60
        status = "✅ Fresh" if age < 14400 else "⚠️ STALE (>4h)"
        print(f"\n🍪 Cookie cache: {status} ({age_hrs:.1f}h old)")
        print(f"   Refresh: python3 /app/.agents/skills/sap/sap_cookie_refresh.py --force")
    else:
        print("\n🍪 Cookie cache: ❌ MISSING")
        print("   Run: python3 /app/.agents/skills/sap/sap_cookie_refresh.py")
    
    # Search for relevant endpoints
    print(f"\n🔍 ENDPOINTS MATCHING '{task}':")
    index = load_index()
    results = search(task, index)
    
    if not results:
        print("  No matching endpoints found. Try broader search terms.")
        print("  Use --list-sections to see all available categories.")
    else:
        for ep in results[:10]:  # Top 10 results
            print(format_result(ep))
            print()
        
        if len(results) > 10:
            print(f"  ... and {len(results) - 10} more results")
    
    # Billing protection reminder
    print("\n🚨 BILLING PROTECTION RULE:")
    print("  NEVER touch credit cards, ACH, AutoPay, or payment methods.")
    print("  Strip billing fields from any SaveClient payload.")
    print("  Only exception: Ethan explicitly names a specific client + action.")
    
    # Drive reminder
    print("\n📁 DRIVE CHECK:")
    print("  Before starting: python3 /app/.agents/skills/drive_check.py sap")
    print("  After discovery: python3 /app/.agents/skills/drive_sync.py '{\"action\":\"sync\",\"paths\":[...]}'")
    
    print("\n" + "=" * 70)

def list_sections(index):
    """List all sections in the API map."""
    print(f"Sections in sap_api_map.md ({len(index['sections'])} total):")
    for i, section in enumerate(index['sections'], 1):
        # Count endpoints in this section
        count = sum(1 for ep in index['endpoints'] if ep.get('section') == section)
        if count > 0:
            print(f"  {i:3d}. {section} ({count} endpoints)")

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    args = sys.argv[1:]
    
    if args[0] == '--rebuild':
        build_index()
        sys.exit(0)
    
    if args[0] == '--list-sections':
        index = load_index()
        list_sections(index)
        sys.exit(0)
    
    if args[0] == '--preflight':
        task = ' '.join(args[1:]) if len(args) > 1 else 'client'
        preflight(task)
        sys.exit(0)
    
    # Regular search
    query = ' '.join(args)
    index = load_index()
    results = search(query, index)
    
    if not results:
        print(f"No endpoints found matching '{query}'.")
        print("Try:")
        print("  --list-sections to see all categories")
        print("  --rebuild to refresh the index")
        print("  --preflight <task> for a full pre-flight check")
        sys.exit(1)
    
    print(f"Found {len(results)} endpoint(s) matching '{query}':\n")
    for ep in results[:15]:
        print(format_result(ep))
        print()
    
    if len(results) > 15:
        print(f"... and {len(results) - 15} more. Refine your search to narrow down.")
    
    print(f"\n💡 Run with --preflight for full auth requirements + billing protection reminder.")

    main()


def search_feature_map(query):
    """Search the SAP Feature Map for feature-level information."""
    feature_map = '/app/.agents/rules/sap_feature_map.md'
    if not os.path.exists(feature_map):
        return []
    
    with open(feature_map, 'r') as f:
        content = f.read()
    
    # Parse table rows
    results = []
    lines = content.split('\n')
    current_section = ""
    query_lower = query.lower()
    terms = query_lower.split()
    
    for line in lines:
        # Track sections
        if line.startswith('## ') and not line.startswith('### '):
            current_section = line.strip('# ').strip()
        elif line.startswith('### '):
            current_section = line.strip('# ').strip()
        
        # Parse table rows with feature info
        if line.startswith('|') and '---' not in line and 'Feature' not in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 5:
                feature = parts[1]
                status = parts[2]
                endpoints = parts[3]
                help_articles = parts[4] if len(parts) > 4 else ''
                notes = parts[5] if len(parts) > 5 else ''
                
                # Score against query
                haystack = (feature + ' ' + endpoints + ' ' + notes).lower()
                score = 0
                for term in terms:
                    if term in feature.lower():
                        score += 10
                    if term in haystack:
                        score += 3
                
                if score > 0:
                    results.append({
                        'feature': feature,
                        'status': status,
                        'endpoints': endpoints,
                        'help_articles': help_articles,
                        'notes': notes,
                        'section': current_section,
                        'score': score
                    })
    
    results.sort(key=lambda x: -x['score'])
    return results


def format_feature_result(r):
    """Format a feature map result for display."""
    lines = []
    status_emoji = {'✅': '✅', '🔶': '🔶', '❌': '❌'}.get(r['status'][:2], r['status'][:2])
    lines.append(f"  {status_emoji} {r['feature']}")
    lines.append(f"     Status: {r['status']}")
    if r['endpoints'] and r['endpoints'] != '—':
        ep = r['endpoints']
        if len(ep) > 150:
            ep = ep[:150] + '...'
        lines.append(f"     Endpoints: {ep}")
    if r['notes'] and r['notes'] != '—':
        notes = r['notes']
        if len(notes) > 150:
            notes = notes[:150] + '...'
        lines.append(f"     Notes: {notes}")
    lines.append(f"     Section: {r['section']}")
    return '\n'.join(lines)


# Override main to include feature map search
_original_main = main

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    args = sys.argv[1:]
    
    if args[0] == '--rebuild':
        build_index()
        sys.exit(0)
    
    if args[0] == '--list-sections':
        index = load_index()
        list_sections(index)
        sys.exit(0)
    
    if args[0] == '--preflight':
        task = ' '.join(args[1:]) if len(args) > 1 else 'client'
        preflight(task)
        sys.exit(0)
    
    # Regular search — now includes feature map
    query = ' '.join(args)
    index = load_index()
    results = search(query, index)
    feature_results = search_feature_map(query)
    
    # Show feature map results first (higher-level context)
    if feature_results:
        print(f"📋 FEATURE MAP results for '{query}' ({len(feature_results)}):\n")
        for r in feature_results[:5]:
            print(format_feature_result(r))
            print()
        if len(feature_results) > 5:
            print(f"  ... and {len(feature_results) - 5} more features\n")
    
    # Then show endpoint results
    if results:
        print(f"📡 ENDPOINT results for '{query}' ({len(results)}):\n")
        for ep in results[:15]:
            print(format_result(ep))
            print()
        if len(results) > 15:
            print(f"  ... and {len(results) - 15} more. Refine your search to narrow down.")
    
    if not results and not feature_results:
        print(f"No results found matching '{query}'.")
        print("Try:")
        print("  --list-sections to see all categories")
        print("  --rebuild to refresh the index")
        print("  --preflight <task> for a full pre-flight check")
        sys.exit(1)
    
    if results and not feature_results:
        print(f"\n💡 No feature map entries found. Run --preflight for full context.")
    elif feature_results:
        print(f"\n💡 Run with --preflight for full auth requirements + billing protection reminder.")

    main()


def search_playbooks(query):
    """Search the SAP Playbooks for workflow sequences."""
    playbook_file = '/app/.agents/rules/sap_playbooks.md'
    if not os.path.exists(playbook_file):
        return []
    
    with open(playbook_file, 'r') as f:
        content = f.read()
    
    # Parse playbook sections
    results = []
    lines = content.split('\n')
    current_playbook = ""
    current_lines = []
    query_lower = query.lower()
    terms = query_lower.split()
    
    for line in lines:
        # Detect playbook headers
        if line.startswith('## ') and not line.startswith('### ') and 'How to Use' not in line and 'Quick Reference' not in line:
            # Save previous playbook
            if current_playbook and current_lines:
                # Score the playbook
                full_text = '\n'.join(current_lines).lower()
                score = 0
                for term in terms:
                    if term in current_playbook.lower():
                        score += 10
                    if term in full_text:
                        score += 2
                if score > 0:
                    results.append({
                        'name': current_playbook,
                        'steps': current_lines[:30],
                        'score': score
                    })
            
            current_playbook = line.strip('# ').strip()
            current_lines = []
        elif current_playbook:
            current_lines.append(line)
    
    # Don't forget the last one
    if current_playbook and current_lines:
        full_text = '\n'.join(current_lines).lower()
        score = 0
        for term in terms:
            if term in current_playbook.lower():
                score += 10
            if term in full_text:
                score += 2
        if score > 0:
            results.append({
                'name': current_playbook,
                'steps': current_lines[:30],
                'score': score
            })
    
    results.sort(key=lambda x: -x['score'])
    return results


def format_playbook_result(r):
    """Format a playbook result for display."""
    lines = []
    lines.append(f"  📋 {r['name']}")
    # Show first few step lines
    step_lines = [l for l in r['steps'] if l.strip() and not l.startswith('**⚠️')][:8]
    for sl in step_lines:
        if sl.startswith('|'):
            lines.append(f"     {sl.strip()}")
    # Show gotchas
    gotchas = [l for l in r['steps'] if l.startswith('**⚠️')]
    if gotchas:
        lines.append(f"     {gotchas[0].strip('*').strip()}")
    return '\n'.join(lines)


# Override main to include playbook search
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    args = sys.argv[1:]
    
    if args[0] == '--rebuild':
        build_index()
        sys.exit(0)
    
    if args[0] == '--list-sections':
        index = load_index()
        list_sections(index)
        sys.exit(0)
    
    if args[0] == '--preflight':
        task = ' '.join(args[1:]) if len(args) > 1 else 'client'
        preflight(task)
        sys.exit(0)
    
    if args[0] == '--playbooks':
        pb_file = '/app/.agents/rules/sap_playbooks.md'
        with open(pb_file, 'r') as f:
            print(f.read())
        sys.exit(0)
    
    # Regular search — includes feature map + playbooks + endpoints
    query = ' '.join(args)
    index = load_index()
    results = search(query, index)
    feature_results = search_feature_map(query)
    playbook_results = search_playbooks(query)
    
    # Show playbooks first (highest-level context)
    if playbook_results:
        print(f"📋 PLAYBOOKS for '{query}' ({len(playbook_results)}):\n")
        for r in playbook_results[:3]:
            print(format_playbook_result(r))
            print()
    
    # Then feature map
    if feature_results:
        print(f"📊 FEATURE MAP for '{query}' ({len(feature_results)}):\n")
        for r in feature_results[:5]:
            print(format_feature_result(r))
            print()
        if len(feature_results) > 5:
            print(f"  ... and {len(feature_results) - 5} more features\n")
    
    # Then endpoint results
    if results:
        print(f"📡 ENDPOINTS for '{query}' ({len(results)}):\n")
        for ep in results[:15]:
            print(format_result(ep))
            print()
        if len(results) > 15:
            print(f"  ... and {len(results) - 15} more. Refine your search to narrow down.")
    
    if not results and not feature_results and not playbook_results:
        print(f"No results found matching '{query}'.")
        print("Try:")
        print("  --list-sections to see all categories")
        print("  --playbooks to see all workflows")
        print("  --rebuild to refresh the index")
        print("  --preflight <task> for a full pre-flight check")
        sys.exit(1)
    
    print(f"\n💡 Run with --preflight for full auth requirements + billing protection reminder.")

if __name__ == '__main__':
    main()
