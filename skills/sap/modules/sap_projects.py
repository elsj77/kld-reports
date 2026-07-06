"""
sap_projects.py — Project Operations
Endpoints: ProjectListWs (4 ops), ProjectEditWs (1 op),
           v3/Scheduling/ProjectsWs (8 ops)

NOTE: KLD currently has 0 active projects — ProjectListWs.GetProjects returns
{Projects:[], ProjectTotal:0}. This module is complete for if/when projects are used.

ProjectListWs ops: GetProjects, DeleteProjects, UpdateProjectStatus,
                   GetDefaultProjectInvoicingFields
ProjectEditWs ops: GenerateProjectInvoice
v3/Scheduling/ProjectsWs ops: GetProjects, DeleteProjects, UpdateProjectStatus,
                                GetDefaultProjectInvoicingFields,
                                GetInvoiceProjectMilestoneList,
                                GetServiceProductList, GetClientList,
                                GetMoveToResourceList
"""
from .sap_core import SAPClient, get_sap, NULL_GUID


class ProjectsAPI:
    def __init__(self, sap=None):
        self.sap = sap or get_sap()

    # ─── LIST / QUERY ─────────────────────────────────────────────────────────

    def get_all(self, active_tab=0, show_completed=False, max_rows=29,
                client_id=None, resource_ids=None, service_ids=None,
                map_code="", address="", city="", zip_code="",
                start_row=1):
        """Get project list with filters.
        active_tab: 0=active, 1=completed
        Returns: {Projects: [{ProjectID, ProjectName, ClientName, Status, ...}],
                  ProjectTotal}
        NOTE: KLD has 0 projects — will return empty list.
        """
        return self.sap.post("/WebServices/ProjectListWs.asmx/GetProjects", {
            "Input": {
                "ResourceIDs": resource_ids or [],
                "ServiceIDs": service_ids or [],
                "MapCode": map_code,
                "CustomerID": client_id or NULL_GUID,
                "Address": address,
                "City": city,
                "Zip": zip_code,
                "ShowCompleted": show_completed,
                "StartRow": start_row,
                "MaxRows": max_rows,
                "ActiveTab": active_tab
            }
        })

    def get_all_v3(self, active_tab=0, show_completed=False, max_rows=29,
                   client_id=None, resource_ids=None, service_ids=None):
        """Get project list via v3 Scheduling/ProjectsWs endpoint."""
        return self.sap.post("/v3/WebServices/Scheduling/ProjectsWs.asmx/GetProjects", {
            "Input": {
                "ResourceIDs": resource_ids or [],
                "ServiceIDs": service_ids or [],
                "MapCode": "",
                "CustomerID": client_id or NULL_GUID,
                "Address": "",
                "City": "",
                "Zip": "",
                "ShowCompleted": show_completed,
                "StartRow": 1,
                "MaxRows": max_rows,
                "ActiveTab": active_tab
            }
        })

    # ─── STATUS ───────────────────────────────────────────────────────────────

    def update_status(self, project_id, status):
        """Update project status.
        status: integer status code
        """
        return self.sap.post("/WebServices/ProjectListWs.asmx/UpdateProjectStatus", {
            "ProjectID": project_id,
            "Status": status
        })

    def delete(self, project_ids):
        """Delete projects by GUID list."""
        return self.sap.post("/WebServices/ProjectListWs.asmx/DeleteProjects", {
            "ProjectIDs": project_ids
        })

    # ─── INVOICING ────────────────────────────────────────────────────────────

    def get_default_invoicing_fields(self):
        """Get default invoicing field values for new project invoices."""
        return self.sap.post("/WebServices/ProjectListWs.asmx/GetDefaultProjectInvoicingFields", {})

    def get_milestones(self):
        """Get invoice project milestone list."""
        return self.sap.post("/WebServices/ProjectListWs.asmx/GetInvoiceProjectMilestoneList", {})

    def generate_invoice(self, project_data):
        """Generate invoice for a project.
        project_data: invoice generation payload (use get_default_invoicing_fields() as guide)
        """
        return self.sap.post("/WebServices/ProjectEditWs.asmx/GenerateProjectInvoice", project_data)

    # ─── LOOKUP LISTS (v3) ────────────────────────────────────────────────────

    def get_service_product_list(self):
        """Get service/product options for project creation (v3).
        Returns available services and products that can be added to a project.
        """
        return self.sap.post("/v3/WebServices/Scheduling/ProjectsWs.asmx/GetServiceProductList", {})

    def get_client_list(self):
        """Get client list for project assignment dropdown (v3)."""
        return self.sap.post("/v3/WebServices/Scheduling/ProjectsWs.asmx/GetClientList", {})

    def get_resource_list(self):
        """Get resource list for project assignment (v3)."""
        return self.sap.post("/v3/WebServices/Scheduling/ProjectsWs.asmx/GetMoveToResourceList", {})
