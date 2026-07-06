"""
sap_dispatch.py — Dispatch Board Operations
Endpoints: ScheduledWorkWs (60+ ops confirmed)

STATUS CODES:
  -1 = Waiting List
   0 = Unscheduled
   1 = Pending/Scheduled
   2 = On Route
   3 = Completed
   4 = Cancelled
   5 = Skipped
"""
from .sap_core import SAPClient, get_sap, NULL_GUID
import datetime


class DispatchAPI:
    def __init__(self, sap=None):
        self.sap = sap or get_sap()

    # ─── QUERY ───────────────────────────────────────────────────────────────

    def query(self, start_date=None, end_date=None, crew_ids=None, service_ids=None,
              map_code="", is_snow=False, is_waiting_list=False, schedule_status="0",
              resource_id=1, screen_view_id=NULL_GUID, divisions=None, tags=None,
              client="", address="", city=""):
        """Query the dispatch board — THE primary data fetch.
        Returns: {ScheduledItems: [{ClientID, Client, Address, Service,
                  AssignedResourceIDs, Date, Status, WorkOrderID, ...}]}
        Tip: Pass client='<name>' to filter by client without date range restrictions.
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

        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/Query", {
            "QueryData": {
                "StartDate": bd(start_date),
                "EndDate": bd(end_date),
                "CustomFields": [],
                "CrewIDs": crew_ids or [],
                "ServiceIDs": service_ids or [],
                "Divisions": divisions or [],
                "Tags": tags or [],
                "TicketTypes": [],
                "ResourceTags": "",
                "ProximityMiles": "5.00",
                "ProximityAddress": "",
                "FilterProximity": False,
                "ResourceID": resource_id,
                "MapCode": map_code,
                "MapCodeOperator": "0",
                "Address": address,
                "Client": client,
                "City": city,
                "Zip": "",
                "DOW": -1,
                "IncludeUnassignedWork": False,
                "ScheduleStatus": schedule_status,
                "Priority": "0",
                "MultiDay": False,
                "UseMinDays": True,
                "DispatchedOnly": False,
                "IsWaitingList": is_waiting_list,
                "IsSnow": is_snow,
                "DispatchID": NULL_GUID,
                "ScreenViewID": screen_view_id,
                "IsCloseOutDay": False,
                "ShowProductTotals": True,
                "LoadAppointmentTimes": False
            },
            "OnNewDispatchBoard": True
        })

    def query_for_client(self, client_name, days_ahead=60):
        """Convenience: get all upcoming scheduled visits for a client by name."""
        today = datetime.date.today()
        end = today + datetime.timedelta(days=days_ahead)
        return self.query(start_date=today, end_date=end, client=client_name)

    # ─── SCREEN VIEWS ────────────────────────────────────────────────────────

    def get_screen_views(self):
        """Get saved dispatch board screen views.
        Known views: acefdfad=Dispatch Board, 168090e3=Close Out Day
        """
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/GetScreenViewList", {
            "NewDispatchBoard": True
        })

    def load_screen_view(self, view_id):
        """Load a saved screen view."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/LoadScreenView", {
            "ItemID": view_id
        })

    def get_screen_view_filters(self, view_id):
        """Get filters for a saved screen view."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/GetScreenViewFilters", {
            "ScreenViewID": view_id
        })

    def save_screen_view(self, view_data):
        """Save a dispatch board screen view."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/SaveScreenView", view_data)

    def delete_screen_view(self, view_id):
        """Delete a screen view."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/DeleteView", {
            "ViewID": view_id
        })

    # ─── ASSIGNMENT ──────────────────────────────────────────────────────────

    def get_assignment_data(self, work_order_id):
        """Get assignment data for a dispatch item."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/GetAssignmentData", {
            "WorkOrderID": work_order_id
        })

    def save_assignment(self, assignment_data):
        """Save job resource/crew assignment."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/SaveAssignmentData", assignment_data)

    def change_assignment(self, assignment_data):
        """Change job assignment (move to different crew)."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/ChangeAssignment", assignment_data)

    # ─── STATUS CHANGES ───────────────────────────────────────────────────────

    def mark_completed(self, work_order_data):
        """Mark job(s) as completed (Status=3)."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/MarkAsCompleted", work_order_data)

    def mark_cancelled(self, work_order_data):
        """Mark job(s) as cancelled (Status=4)."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/MarkAsCancelled", work_order_data)

    def mark_skipped(self, work_order_data):
        """Mark job(s) as skipped (Status=5)."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/MarkAsSkipped", work_order_data)

    def move_to_pending(self, work_order_data):
        """Move job(s) to pending/scheduled (Status=1)."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/MoveToPending", work_order_data)

    def move_to_route(self, work_order_data):
        """Move job(s) to on-route (Status=2)."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/MoveToRoute", work_order_data)

    def move_to_waiting_list(self, work_order_data):
        """Move job(s) to waiting list (Status=-1)."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/MoveToWaitingList", work_order_data)

    def skip_service(self, skip_data):
        """Skip a service occurrence."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/SkipService", skip_data)

    # ─── WORK ORDERS ─────────────────────────────────────────────────────────

    def create_work_orders(self, dispatch_item_ids):
        """Create work orders from dispatch items."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/CreateWorkOrders", {
            "DispatchItemIDs": dispatch_item_ids
        })

    def invoice_work_orders(self, work_order_ids):
        """Invoice work orders."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/InvoiceWorkOrders", {
            "WorkOrderIDs": work_order_ids
        })

    def invoice_on_complete(self, work_order_data):
        """Auto-invoice work orders on completion."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/InvoiceWorkOrdersOnComplete", work_order_data)

    # ─── APPOINTMENTS ─────────────────────────────────────────────────────────

    def get_appointment_data(self, appointment_id):
        """Get appointment details."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/GetAppointmentData", {
            "AppointmentID": appointment_id
        })

    def save_appointment(self, appointment_data):
        """Save an appointment."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/SaveAppointmentData", appointment_data)

    # ─── NOTES ────────────────────────────────────────────────────────────────

    def get_note(self, work_order_id):
        """Get note for a dispatch item."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/GetNoteData", {
            "WorkOrderID": work_order_id
        })

    def save_note(self, note_data):
        """Save note on a dispatch job."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/SaveNoteData", note_data)

    # ─── ROUTE ────────────────────────────────────────────────────────────────

    def update_route_order(self, route_data):
        """Reorder stops on a route."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/UpdateRouteOrder", route_data)

    def optimize_stops(self, resource_id, stop_ids):
        """Optimize route stop order."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/OptimizeResourceStops", {
            "ResourceID": resource_id,
            "StopIDs": stop_ids
        })

    def export_schedule(self, export_data):
        """Export schedule to file."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/ExportSchedule", export_data)

    # ─── SNOW ─────────────────────────────────────────────────────────────────

    def get_snow_dispatches(self):
        """Get snow dispatches list."""
        return self.sap.post("/webservices/ScheduledWorkWs.asmx/GetSnowDispatchesList", {})

    def get_snow_dispatch_data(self, dispatch_id):
        """Get snow-specific dispatch data."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/GetSnowDispatchData", {
            "DispatchID": dispatch_id
        })

    def save_snow_dispatch(self, dispatch_data):
        """Save a snow dispatch."""
        return self.sap.post("/WebServices/ScheduledWorkWs.asmx/SaveSnowDispatch", dispatch_data)

    # ─── HELPERS ─────────────────────────────────────────────────────────────

    def get_today(self, crew_ids=None):
        """Shortcut: get today's dispatch board."""
        return self.query(crew_ids=crew_ids)

    def get_week(self, crew_ids=None):
        """Shortcut: get this week's dispatch board."""
        today = datetime.date.today()
        monday = today - datetime.timedelta(days=today.weekday())
        friday = monday + datetime.timedelta(days=4)
        return self.query(start_date=monday, end_date=friday, crew_ids=crew_ids)
