# KLD Skills — SAP & LeanScaper

Shared skill library for Kootenay Lawn Doctor operations.
Available across all Superagent instances, CI workflows, and Base44 apps.

## SAP Skills (`sap/`)
- `sap_auth.py` — 4-tier auth (Browserbase, JS fetch, cookie replay, Playwright)
- `sap_endpoint_lookup.py` — Search 673+ endpoints across 12K-line API map
- `sap_sniff_base.py` — Reusable Playwright sniffing framework (SniffSession class)
- `auto_update_hours.py` — Data-driven BudgetedHours + crew size updates
- `sync_pp_to_sheets.py` — Sync SAP timesheets to Google Sheets pay period tabs

## LeanScaper Skills (`leanscaper/`)
- `ls_auth.py` — Auth0 email/password + X-Organization-Id header routing
- `refresh_token.py` — Full JWT refresh flow via Browserbase CDP
- `ls_data.py` — Pull boards, employees, goals, huddles, inventory
- `ls_board_card.py` — Board card CRUD (6 boards with column IDs)
- `ls_board_cards.py` — SAP→LeanScaper board bridge
- `push_scorecard.py` — SAP KPIs → LeanScaper scorecard goals
- `ls_scorecard_feed.py` — Push SAP values to scorecard
- `query_agent.py` — Query any LS agent with KLD context injection
- `field_request_router.py` — Route WhatsApp messages to LS boards

## Required Env Vars
- `SAP_USERNAME`, `SAP_PASSWORD` — SAP login
- `LEANSCAPER_EMAIL`, `LEANSCAPER_PASSWORD` — LS Auth0 login
- `LEANSCAPER_JWT`, `LEANSCAPER_JWT_EXPIRES` — LS token (auto-refreshed)
- `LEANSCAPER_ORG_UUID` — `09c7c652-a7c7-492e-a65b-759db4ddba45` (KLD Inc - 2)
- `GITHUB_ACCESS_TOKEN` — For CI workflows
