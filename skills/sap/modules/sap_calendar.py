"""
sap_calendar.py — Calendar & Scheduling Operations
Endpoints: Calendar.asmx (8 ops), SchedulingBFF (2 ops), ScriptServicesWs (1 op)

NOTE: Calendar.asmx/Query uses the same payload shape as ScheduledWorkWs/Query
but with different fields (Activities instead of TicketTypes, has CalendarView, no ScheduleStatus).
"""
from .sap_core import SAPClient, get_sap, NULL_GUID
import datetime


class CalendarAPI:
    def __init__(self, sap=None):
        self.sap = sap or get_sap()

    # ─── SETTINGS & VIEWS ────────────────────────────────────────────────────

    def get_settings(self):
        """Get calendar page settings.
        Returns: {EventFormat, EventColorFormat, ShowNonAppointments, ConfirmReassignment,
                  EventDetailsLine1/2/3}
        """
        return self.sap.post("/WebServices/Calendar.asmx/GetCalendarSettings", {})

    def get_screen_views(self):
        """Get saved calendar screen views."""
        return self.sap.post("/WebServices/Calendar.asmx/GetScreenViewList", {})

    def load_screen_view(self, view_id):
        """Load a saved calendar screen view by GUID."""
        return self.sap.post("/WebServices/Calendar.asmx/LoadScreenView", {
            "ItemID": view_id
        })

    def get_screen_view_filters(self, view_id=None):
        """Get filter options for a calendar screen view."""
        return self.sap.post("/WebServices/Calendar.asmx/GetScreenViewFilters", {
            "ScreenViewID": view_id or NULL_GUID
        })

    def get_generic_screen_views(self, screen_view_type=9):
        """Get screen views by type via ScreenViewWs.
        screen_view_type: 9=scheduling calendar
        """
        return self.sap.post("/WebServices/ScreenViewWs.asmx/GetScreenViews", {
            "InputData": {"ScreenViewTypeValue": screen_view_type}
        })

    # ─── QUERY ───────────────────────────────────────────────────────────────

    def query(self, start_date=None, end_date=None, crew_ids=None, service_ids=None,
              calendar_view="Month"):
        """Query calendar events for a date range.
        NOTE: Uses Activities (not TicketTypes), no ScheduleStatus field.
        calendar_view: 'Month' | 'Week' | 'Day'
        """
        today = datetime.date.today()
        if not start_date:
            start_date = today
        if not end_date:
            end_date = today

        def bd(d):
            if isinstance(d, str):
                d = datetime.date.fromisoformat(d)
            return {"Month": d.month, "Day": d.day, "Year": d.year}

        return self.sap.post("/WebServices/Calendar.asmx/Query", {
            "QueryData": {
                "StartDate": bd(start_date),
                "EndDate": bd(end_date),
                "CrewIDs": crew_ids or [],
                "ServiceIDs": service_ids or [],
                "Activities": [],
                "MapCode": "",
                "IsSnow": False,
                "CalendarView": calendar_view,
                "ResourceID": 1,
                "ScreenViewID": NULL_GUID
            }
        })

    def get_hud_items(self, page=0):
        """Get calendar HUD items for My Day view.
        Returns upcoming appointments/events for the day.
        """
        return self.sap.post("/WebServices/ScriptServicesWs.asmx/GetCalendarHudItemsForMyDay", {
            "request": {"Page": page}
        })

    # ─── EVENT CRUD ──────────────────────────────────────────────────────────

    def get_event(self, event_id):
        """Get a calendar event by ID."""
        return self.sap.post("/WebServices/Calendar.asmx/GetCalendarEventData", {
            "EventID": event_id
        })

    def save_event(self, event_data):
        """Create or update a calendar event.
        event_data: full event payload (get from get_event() to understand shape)
        """
        return self.sap.post("/WebServices/Calendar.asmx/SaveCalendarEventData", event_data)

    def delete_all_occurrences(self, event_id):
        """Delete all occurrences of a recurring calendar event."""
        return self.sap.post("/WebServices/Calendar.asmx/DeleteAllOccurrences", {
            "EventID": event_id
        })

    # ─── SCHEDULING BFF ──────────────────────────────────────────────────────

    def save_bff_event(self, event_data):
        """Save an onsite visit / appointment via SchedulingBFF.
        Used for creating onsite visit events linked to tickets.
        event_data: payload shape still being discovered (see api map SchedulingBFF section)
        """
        return self.sap.post("/SchedulingBFF/CalendarEvent/Save", event_data)

    def get_account_address(self, customer_job_id):
        """Get account address for calendar event scheduling.
        customer_job_id: CustomerJobID (NOT CustomerID)
        Returns: {Address, City, State, PostalCode, Lat, Lng, ...}
        """
        return self.sap.post("/SchedulingBFF/CalendarEvent/GetAccountAddress", {
            "customerJobId": customer_job_id
        })
