"""
sap_employees.py — Employee Operations
Endpoints: EmployeesWs (legacy .asmx — 34 ops confirmed),
           v3/Team/EmployeesWs.asmx (note/touchpoint ops)

NOTE: v3/Team/EmployeesWs.asmx/GetEmployees has a server-side null ref bug.
Use legacy /webservices/EmployeesWs.asmx/GetEmployees instead.
"""
from .sap_core import SAPClient, get_sap, NULL_GUID


class EmployeesAPI:
    def __init__(self, sap=None):
        self.sap = sap or get_sap()

    # ─── LIST / GET ──────────────────────────────────────────────────────────

    def get_all(self, tab=0, start_row=1, max_rows=100, name="", user_type="0"):
        """List all employees.
        tab: 0=all, 1=active, 2=inactive
        user_type: '0'=all types
        Returns: {EmployeeTotal, Employees: [{EmployeeID, Name, UserType, ...}]}
        NOTE: Uses legacy endpoint — v3 has a null ref bug.
        """
        return self.sap.post("/webservices/EmployeesWs.asmx/GetEmployees", {
            "Input": {
                "Tab": tab,
                "StartRow": start_row,
                "MaxRows": max_rows,
                "Name": name,
                "UserType": user_type
            }
        })

    def get(self, employee_id):
        """Get full employee record.
        ALWAYS GET before SaveEmployee — partial saves overwrite all fields.
        Returns complete employee object with all fields.
        """
        return self.sap.post("/webservices/EmployeesWs.asmx/GetEmployeeData", {
            "EmployeeID": employee_id
        })

    def get_avatar(self, employee_id):
        """Get employee avatar/profile photo info."""
        return self.sap.post("/webservices/EmployeesWs.asmx/GetEmployeeAvatar", {
            "EmployeeID": employee_id
        })

    def get_user_avatar(self, user_id):
        """Get user avatar by user ID."""
        return self.sap.post("/v3/WebServices/Team/EmployeesWs.asmx/GetUserAvatar", {
            "UserID": user_id
        })

    # ─── SAVE / STATUS ────────────────────────────────────────────────────────

    def save(self, employee_data):
        """Create or update an employee.
        NULL_GUID as EmployeeID = create new.
        ALWAYS call get() first when updating to avoid overwriting fields.
        Returns: {EmployeeID, errors}
        NOTE: HTTP 500 on create may still have saved — search by name to confirm.
        """
        return self.sap.post("/webservices/EmployeesWs.asmx/SaveEmployee", {
            "Input": employee_data
        })

    def update_status(self, employee_ids, status):
        """Activate or deactivate employees.
        status: 1=active, 0=inactive
        """
        return self.sap.post("/webservices/EmployeesWs.asmx/UpdateEmployeeStatus", {
            "EmployeeIDs": employee_ids,
            "Status": status
        })

    def delete(self, employee_ids):
        """Delete employees."""
        return self.sap.post("/webservices/EmployeesWs.asmx/DeleteEmployees", {
            "EmployeeIDs": employee_ids
        })

    def convert_applicant(self, applicant_id):
        """Convert an applicant to an employee."""
        return self.sap.post("/webservices/EmployeesWs.asmx/ConvertApplicantToEmployee", {
            "ApplicantID": applicant_id
        })

    # ─── ASSIGNMENTS ─────────────────────────────────────────────────────────

    def update_assignments(self, employee_id, assigned_crew_id):
        """Reassign employee to a different crew.
        assigned_crew_id: crew/resource GUID
        """
        return self.sap.post("/webservices/EmployeesWs.asmx/UpdateAssignments", {
            "EmployeeID": employee_id,
            "AssignedCrew": assigned_crew_id
        })

    def get_reassignment_count(self, employee_id):
        """Get reassignment count for an employee."""
        return self.sap.post("/v3/WebServices/Team/EmployeesWs.asmx/GetReassignmentCount", {
            "EmployeeID": employee_id
        })

    def get_move_to_resource_list(self):
        """Get list of resources an employee can be moved to."""
        return self.sap.post("/v3/WebServices/Team/EmployeesWs.asmx/GetMoveToResourceList", {})

    # ─── SCHEDULE ────────────────────────────────────────────────────────────

    def get_schedule(self, employee_id):
        """Get employee resource schedule."""
        return self.sap.post("/v3/WebServices/Team/EmployeesWs.asmx/GetResourceSchedule", {
            "EmployeeID": employee_id
        })

    def get_default_schedule(self, employee_id):
        """Get employee default schedule."""
        return self.sap.post("/v3/WebServices/Team/EmployeesWs.asmx/GetDefaultSchedule", {
            "EmployeeID": employee_id
        })

    def save_scheduled_day(self, schedule_data):
        """Save a scheduled work day for an employee."""
        return self.sap.post("/v3/WebServices/Team/EmployeesWs.asmx/SaveScheduledDay", schedule_data)

    def load_scheduled_day(self, day_data):
        """Load a scheduled day's data."""
        return self.sap.post("/v3/WebServices/Team/EmployeesWs.asmx/LoadScheduledDayData", day_data)

    def save_scheduled_day_override(self, override_data):
        """Save a scheduled day override (exception to regular schedule)."""
        return self.sap.post("/v3/WebServices/Team/EmployeesWs.asmx/SaveScheduledDayOverride", override_data)

    # ─── TIME OFF ─────────────────────────────────────────────────────────────

    def get_time_off(self, employee_id):
        """Get employee time off requests."""
        return self.sap.post("/v3/WebServices/Team/EmployeesWs.asmx/GetEmployeeTimeOff", {
            "EmployeeID": employee_id
        })

    def get_vacation_days(self, employee_id):
        """Get employee vacation day balance."""
        return self.sap.post("/v3/WebServices/Team/EmployeesWs.asmx/GetEmployeeVacationDays", {
            "EmployeeID": employee_id
        })

    def get_manager_time_off_requests(self):
        """Get all pending time off requests (manager view)."""
        return self.sap.post("/v3/WebServices/Team/EmployeesWs.asmx/GetManagerTimeOffRequests", {})

    # ─── TIMESHEETS ──────────────────────────────────────────────────────────

    def get_timesheet_records(self, employee_id):
        """Get timesheet records for an employee."""
        return self.sap.post("/v3/WebServices/Team/EmployeesWs.asmx/GetTimesheetRecords", {
            "EmployeeID": employee_id
        })

    def get_scheduled_work(self, employee_id):
        """Get scheduled work items for an employee."""
        return self.sap.post("/v3/WebServices/Team/EmployeesWs.asmx/GetScheduledWork", {
            "EmployeeID": employee_id
        })

    # ─── TIMELINE / NOTES ────────────────────────────────────────────────────

    def get_timeline(self, employee_id):
        """Get all timeline items for an employee."""
        return self.sap.post("/v3/WebServices/Team/EmployeesWs.asmx/GetTimelineItems", {
            "EmployeeID": employee_id
        })

    def get_timeline_by_type(self, employee_id, item_type):
        """Get timeline items of a specific type for an employee."""
        return self.sap.post("/v3/WebServices/Team/EmployeesWs.asmx/GetTimelineItemsByType", {
            "EmployeeID": employee_id,
            "Type": item_type
        })

    def get_ticket_detail(self, ticket_detail_id):
        """Get a modified ticket detail item with notes.
        ticket_detail_id: GUID of the detail record
        """
        return self.sap.post("/webservices/EmployeesWs.asmx/GetModifiedTicketDetailItem", {
            "TicketDetailID": ticket_detail_id
        })

    def get_touchpoint_item(self, touchpoint_id):
        """Get a modified touchpoint item."""
        return self.sap.post("/v3/WebServices/Team/EmployeesWs.asmx/GetModifiedTouchpointItem", {
            "TouchpointID": touchpoint_id
        })

    def save_note(self, note_data):
        """Save a note on an employee timeline."""
        return self.sap.post("/v3/WebServices/Team/EmployeesWs.asmx/SaveNoteItem", note_data)

    def delete_note(self, note_guid):
        """Delete a note from an employee timeline."""
        return self.sap.post("/v3/WebServices/Team/EmployeesWs.asmx/DeleteNoteItem", {
            "NoteID": note_guid
        })

    def save_touchpoint(self, touchpoint_data):
        """Save a touchpoint on an employee."""
        return self.sap.post("/v3/WebServices/Team/EmployeesWs.asmx/SaveTouchpoint", touchpoint_data)

    # ─── RATINGS / CUSTOM FIELDS ─────────────────────────────────────────────

    def get_rating(self, employee_id):
        """Get employee performance rating."""
        return self.sap.post("/v3/WebServices/Team/EmployeesWs.asmx/GetEmployeeRating", {
            "EmployeeID": employee_id
        })

    def get_damage_cases(self, employee_id):
        """Get damage cases associated with an employee."""
        return self.sap.post("/v3/WebServices/Team/EmployeesWs.asmx/GetEmployeeDamageCases", {
            "EmployeeID": employee_id
        })

    def get_custom_fields(self):
        """Get custom field definitions for employees."""
        return self.sap.post("/v3/WebServices/Team/EmployeesWs.asmx/GetCustomFieldList", {})

    def get_custom_fields_view(self, employee_id):
        """Get custom field values for a specific employee."""
        return self.sap.post("/v3/WebServices/Team/EmployeesWs.asmx/GetEmployeeViewCustomFieldList", {
            "EmployeeID": employee_id
        })

    def get_estimate_list(self, employee_id):
        """Get estimate list for an employee (sales rep view)."""
        return self.sap.post("/v3/WebServices/Team/EmployeesWs.asmx/GetEmployeeEstimateList", {
            "EmployeeID": employee_id
        })
