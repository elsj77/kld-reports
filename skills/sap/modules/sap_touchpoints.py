"""
sap_touchpoints.py — Touchpoint (CRM Activity) Operations
Endpoints: MSTouchpointStatusWs (5 ops), ClientUpdateWs, EmployeesWs, VendorsWs

Touchpoints represent CRM activities: phone calls, emails, site visits,
sales calls, etc. They appear on client/employee/vendor timelines.

ENTITY TYPES: 1=Client, 2=Employee, 3=Vendor
"""
from .sap_core import SAPClient, get_sap, NULL_GUID


class TouchpointsAPI:
    def __init__(self, sap=None):
        self.sap = sap or get_sap()

    # ─── METADATA ─────────────────────────────────────────────────────────────

    def get_types(self):
        """Get all touchpoint types (phone call, email, site visit, etc.)
        Returns: [{ID, Name, Icon, ...}]
        """
        return self.sap.post(
            "/v3/WebServices/MasterSettings/MSTouchpointStatusWs.asmx/GetTouchpointTypeList", {}
        )

    # ─── READ ─────────────────────────────────────────────────────────────────

    def get(self, entity_id, entity_type=1):
        """Get touchpoints for an entity.
        entity_type: 1=Client, 2=Employee, 3=Vendor
        """
        return self.sap.post(
            "/v3/WebServices/MasterSettings/MSTouchpointStatusWs.asmx/GetTouchpoints",
            {"EntityID": entity_id, "EntityType": entity_type}
        )

    # ─── SAVE ─────────────────────────────────────────────────────────────────

    def save(self, touchpoint_data):
        """Save a touchpoint via MSTouchpointStatusWs (generic).
        touchpoint_data: full touchpoint payload
        """
        return self.sap.post(
            "/v3/WebServices/MasterSettings/MSTouchpointStatusWs.asmx/SaveTouchpoint",
            touchpoint_data
        )

    def save_on_client(self, client_guid, touchpoint_type_id, notes="", subject="",
                       contact_date=None, assigned_to=None):
        """Save a touchpoint on a client via ClientUpdateWs.
        touchpoint_type_id: GUID from get_types()
        contact_date: dict {Month, Day, Year} or None for today
        """
        from .sap_core import USER_ID
        import datetime
        today = datetime.date.today()
        date = contact_date or {"Month": today.month, "Day": today.day, "Year": today.year}
        return self.sap.post("/webservices/ClientUpdateWs.asmx/SaveTouchpoint", {
            "TouchpointData": {
                "EntityID": client_guid,
                "EntityType": 1,
                "TouchpointTypeID": touchpoint_type_id,
                "Subject": subject,
                "Notes": notes,
                "ContactDate": date,
                "AssignedUserID": assigned_to or USER_ID
            }
        })

    def save_on_employee(self, employee_guid, touchpoint_data):
        """Save a touchpoint on an employee."""
        return self.sap.post(
            "/v3/WebServices/Team/EmployeesWs.asmx/SaveTouchpoint",
            touchpoint_data
        )

    def save_on_vendor(self, vendor_guid, touchpoint_data):
        """Save a touchpoint on a vendor."""
        return self.sap.post(
            "/v3/WebServices/Team/VendorsWs.asmx/SaveTouchpoint",
            touchpoint_data
        )

    # ─── STATUS / DELETE ──────────────────────────────────────────────────────

    def update_status(self, touchpoint_id, status):
        """Update touchpoint status (e.g. mark as completed)."""
        return self.sap.post(
            "/v3/WebServices/MasterSettings/MSTouchpointStatusWs.asmx/UpdateTouchpointStatus",
            {"TouchpointID": touchpoint_id, "Status": status}
        )

    def delete(self, touchpoint_ids):
        """Delete touchpoints by GUID list."""
        return self.sap.post(
            "/v3/WebServices/MasterSettings/MSTouchpointStatusWs.asmx/DeleteTouchpoints",
            {"TouchpointIDs": touchpoint_ids}
        )

    # ─── HELPERS ─────────────────────────────────────────────────────────────

    def log_call(self, client_guid, notes="", call_type_id=None):
        """Shortcut: log a phone call touchpoint on a client.
        call_type_id: touchpoint type GUID for 'Phone Call' (get from get_types()).
        """
        return self.save_on_client(
            client_guid=client_guid,
            touchpoint_type_id=call_type_id or NULL_GUID,
            notes=notes,
            subject="Phone Call"
        )

    def log_site_visit(self, client_guid, notes="", visit_type_id=None):
        """Shortcut: log a site visit touchpoint on a client."""
        return self.save_on_client(
            client_guid=client_guid,
            touchpoint_type_id=visit_type_id or NULL_GUID,
            notes=notes,
            subject="Site Visit"
        )
