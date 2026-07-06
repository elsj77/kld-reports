"""
sap_tickets.py — Ticket / To-Do / CRM Activity Operations
Endpoints:
  CRMBFF/TicketList   — list, search, query, totals
  CRMBFF/TicketEdit   — create, update, delete, assign, status, timer
  CRMBFF/TicketReview — full ticket overlay, watchers, conversation, related items
  TicketsWs.asmx      — categories, permissions, ticket types
  EmployeesWs.asmx    — GetModifiedTicketDetailItem (ticket detail with notes)

NOTE: CRMBFF/TicketList/Query currently returns a server-side error from the
SAP microservice at app.sa.prod.local:3200 — use MyDay_GetTickets or QueryTotals+QueryByIDs instead.

KLD Ticket Categories (19 total — from TicketEdit_TicketCategoryDropdown_GetByCompany):
  Account Issue, Reschedule Request, Accounting, Other, Upsell, Terminate Service,
  Change Service, Cancel Request, Damage Case, Marketing, Sales, Operations,
  HR, Equipment, Safety, Quality, Collections, Complaint, Referral
"""
from .sap_core import SAPClient, get_sap, NULL_GUID


class TicketsAPI:
    def __init__(self, sap=None):
        self.sap = sap or get_sap()

    # ─── LIST / SEARCH ────────────────────────────────────────────────────────

    def my_day(self, max_rows=25, all_tickets=False, item_type="Today"):
        """Get tickets for My Day view.
        item_type: 'Today' | 'Overdue' | 'Upcoming'
        """
        return self.sap.post("/CRMBFF/TicketList/MyDay_GetTickets", {
            "QueryInput": {
                "MaxRows": max_rows,
                "AllTickets": all_tickets,
                "StartingRow": 0,
                "TicketItemType": item_type
            }
        })

    def query_totals(self, start_date=None, end_date=None, filters=None):
        """Get ticket totals + all TicketIDs. Use this instead of Query (server bug).
        Returns: {TicketIDs: [...], Total: N}
        """
        no_date = {"Month": -1, "Day": -1, "Year": -1}
        return self.sap.post("/CRMBFF/TicketList/QueryTotals", {
            "QueryInput": {
                "StartRow": 1,
                "Max": 22,
                "StartDate": start_date or no_date,
                "EndDate": end_date or no_date,
                "ScreenViewFilterTypes": filters or [],
                "SortedColumns": []
            }
        })

    def query_by_ids(self, ticket_ids):
        """Get tickets by list of GUIDs.
        ticket_ids: list of ticket GUID strings
        """
        return self.sap.post("/CRMBFF/TicketList/QueryByIDs", {
            "IDs": ticket_ids
        })

    def global_search(self, search_string, start_row=1, max_rows=22):
        """Global full-text search across all tickets."""
        return self.sap.post("/CRMBFF/TicketList/GlobalSearch_TicketsQuery", {
            "QueryInput": {
                "SearchString": search_string,
                "StartRow": start_row,
                "Max": max_rows
            }
        })

    def global_search_totals(self, search_string):
        """Get totals for a global ticket search."""
        return self.sap.post("/CRMBFF/TicketList/GlobalSearch_TicketsQueryTotals", {
            "QueryInput": {
                "SearchString": search_string,
                "StartRow": 1,
                "Max": 1
            }
        })

    def get_ticket_number(self, ticket_id):
        """Get the human-readable ticket number for a ticket GUID."""
        return self.sap.post("/CRMBFF/TicketList/TicketList_GetTicketNumberAsync", {
            "TicketID": ticket_id
        })

    # ─── CREATE / UPDATE ─────────────────────────────────────────────────────

    def create(self, entity_id, subject, body="", category_id=None, assigned_user_id=None,
               due_date="", priority=0, entity_type="Account", ticket_status=0):
        """Create a ticket/to-do on a client or other entity.
        entity_id:   client GUID (or employee/vendor GUID)
        entity_type: 'Account' | 'Employee' | 'Vendor'
        priority:    0=Normal, 1=Low, 2=High
        ticket_status: 0=Open, 1=Completed, 2=Deleted
        category_id: GUID from get_categories() — optional
        """
        from .sap_core import USER_ID
        payload = {
            "Ticket": {
                "CategoryID": category_id,
                "TicketStatus": ticket_status,
                "EntityID": entity_id,
                "EntityType": entity_type,
                "DueDate": due_date,
                "TicketDetail": {
                    "TicketEventType": 1,
                    "Subject": subject,
                    "Body": body,
                    "AssignedUserID": assigned_user_id or USER_ID,
                    "Priority": priority
                }
            }
        }
        return self.sap.post("/CRMBFF/TicketEdit/TicketEdit_Ticket_PostAsync", payload)

    def update_status(self, ticket_id, status):
        """Update ticket status.
        status: 0=Open, 1=Completed, 2=Deleted
        """
        return self.sap.post("/CRMBFF/TicketEdit/TicketStatusUpdate", {
            "TicketID": ticket_id,
            "Status": status
        })

    def assign(self, ticket_id, resource_ids):
        """Assign ticket to one or more resources.
        resource_ids: list of employee/resource GUIDs
        """
        return self.sap.post("/CRMBFF/TicketEdit/UpdateTicketAssignments", {
            "TicketID": ticket_id,
            "ResourceIDs": resource_ids
        })

    def delete(self, ticket_id):
        """Soft-delete a ticket."""
        return self.sap.post("/CRMBFF/TicketEdit/Update_TicketDeleted", {
            "TicketID": ticket_id
        })

    def get_account_context(self, account_id):
        """Get account context for the ticket editor (pre-fills client info).
        account_id: client GUID
        """
        return self.sap.post("/CRMBFF/TicketEdit/TicketEdit_SelectedAccount_Get", {
            "AccountID": account_id
        })

    # ─── TIMER ───────────────────────────────────────────────────────────────

    def timer_start_stop(self, ticket_id, action="start"):
        """Start or stop the stopwatch timer on a ticket.
        action: 'start' | 'stop'
        """
        return self.sap.post("/CRMBFF/TicketEdit/StartStopWatchUpdate", {
            "TicketID": ticket_id,
            "Action": action
        })

    def query_active_timer(self):
        """Get currently active job/ticket timer for the logged-in user."""
        return self.sap.post("/WebServices/TicketDetailTimer.asmx/QueryActiveJob", {})

    # ─── TICKET REVIEW (full overlay) ─────────────────────────────────────────

    def get_overlay_data(self, ticket_id):
        """Get full ticket overlay data — all fields, details, history.
        Returns the same data as the ticket detail overlay in the UI.
        ticket_id: GUID string
        """
        return self.sap.post("/CRMBFF/TicketReview/GetTicketOverlayData", {
            "ticketId": ticket_id
        })

    def get_watch_items(self, ticket_id):
        """Get watchers/followers on a ticket."""
        return self.sap.post(
            "/CRMBFF/TicketReview/TicketReview_TicketWatchItems_GetByTicketIDAsync",
            {"TicketId": ticket_id}
        )

    def get_conversation_participants(self, ticket_id):
        """Get 'in this conversation' participants for a ticket."""
        return self.sap.post(
            "/CRMBFF/TicketReview/TicketReview_InThisConversation_GetByTicketIDAsync",
            {"TicketId": ticket_id}
        )

    def get_related_items(self, ticket_id):
        """Get related items linked to a ticket (jobs, estimates, invoices)."""
        return self.sap.post(
            "/CRMBFF/TicketReview/TicketReview_TicketRelatedItems_GetByTicketIDAsync",
            {"TicketID": ticket_id}
        )

    # ─── TICKET DETAIL (notes/events on a ticket) ─────────────────────────────

    def get_detail_item(self, ticket_detail_id, entity_type="Account"):
        """Get a specific ticket detail item (note/event) with full content.
        ticket_detail_id: GUID of the detail record (from overlay_data)
        Uses EmployeesWs — confirmed working for Account context.
        """
        return self.sap.post(
            "/webservices/EmployeesWs.asmx/GetModifiedTicketDetailItem",
            {"TicketDetailID": ticket_detail_id}
        )

    # ─── LISTS / METADATA ─────────────────────────────────────────────────────

    def get_categories(self):
        """Get all ticket categories for this company (KLD has 19).
        Returns: [{ID, Name, Color, ...}]
        """
        return self.sap.post(
            "/CRMBFF/TicketEdit/TicketEdit_TicketCategoryDropdown_GetByCompany", {}
        )

    def get_permissions(self):
        """Get ticket add permissions for current user."""
        return self.sap.post("/webservices/TicketsWs.asmx/GetAddTicketPermissions", {})

    def get_ticket_types(self):
        """Get ticket type list (Call, Ticket, Ticket or Call)."""
        return self.sap.post("/webservices/TicketsWs.asmx/GetTicketTypeList", {})

    def get_system_types(self):
        """Get system ticket types (6 types)."""
        return self.sap.post("/webservices/TicketsWs.asmx/GetTicketSystemTypeList", {})

    # ─── HELPERS ─────────────────────────────────────────────────────────────

    def complete(self, ticket_id):
        """Mark a ticket as completed (shortcut)."""
        return self.update_status(ticket_id, 1)

    def reopen(self, ticket_id):
        """Reopen a completed ticket."""
        return self.update_status(ticket_id, 0)

    def create_on_client(self, client_guid, subject, body="", category_id=None):
        """Shortcut: create a ticket on a client account."""
        return self.create(
            entity_id=client_guid,
            subject=subject,
            body=body,
            category_id=category_id,
            entity_type="Account"
        )
