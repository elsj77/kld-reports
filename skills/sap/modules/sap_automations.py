"""
sap_automations.py — Marketing Automation & Sales Campaign Operations
Endpoints: AutomationWs (6 working ops), SalesCampaignWs (3 ops)

NOTE: SaveAutomation/GetAutomation/StopAutomation are server-side blocked.
Build automations in the SAP UI — use this module to READ and MANAGE them.
"""
from .sap_core import SAPClient, get_sap, NULL_GUID


class AutomationsAPI:
    def __init__(self, sap=None):
        self.sap = sap or get_sap()

    # ─── AUTOMATIONS ─────────────────────────────────────────────────────────

    def get_all(self, query_selection=0):
        """List all marketing automations.
        query_selection: 0=active only, 1=all (including marketplace/inactive)
        Returns: {ListItems: [{AutomationID, Name, Description, NumberRunning, Active}]}
        """
        return self.sap.post("/webservices/AutomationWs.asmx/GetAutomations", {
            "QuerySelection": query_selection
        })

    def get_counts(self, automation_ids):
        """Get how many clients are currently in each automation.
        automation_ids: list of AutomationID GUIDs
        Returns: {ListItems: [{AutomationID, NumberRunning}]}
        """
        return self.sap.post("/webservices/AutomationWs.asmx/GetAutomationsCount", {
            "AutomationIds": automation_ids
        })

    def get_hud(self, tab=0):
        """Get automations for My Day HUD (active only, with client counts).
        tab: 0=active automations
        """
        return self.sap.post("/webservices/AutomationWs.asmx/GetAutomationsForHUD", {
            "tab": tab
        })

    def check_client_has_running(self, client_guid):
        """Check if a client is currently enrolled in any running automation.
        Returns: {HasRunningAutomations: bool, CanViewAutomations: bool}
        """
        return self.sap.post("/WebServices/AutomationWs.asmx/CheckIfCustomerHasRunningAutomations", {
            "CustomerID": client_guid
        })

    def update_status(self, automation_ids, status):
        """Activate or deactivate automations.
        automation_ids: list of AutomationID GUIDs
        status: 1=active, 0=inactive
        """
        return self.sap.post("/WebServices/Marketing/AutomationWs.asmx/UpdateAutomationStatus", {
            "AutomationIDs": automation_ids,
            "Status": status
        })

    def delete(self, automation_ids):
        """Delete automations.
        automation_ids: list of AutomationID GUIDs
        """
        return self.sap.post("/WebServices/Marketing/AutomationWs.asmx/DeleteAutomations", {
            "AutomationIDs": automation_ids
        })

    def copy(self, automation_id):
        """Copy/duplicate an automation."""
        return self.sap.post("/WebServices/Marketing/AutomationWs.asmx/CopyAutomations", {
            "AutomationID": automation_id
        })

    # ─── SALES CAMPAIGNS ─────────────────────────────────────────────────────

    def get_campaigns(self, active_tab=0, start_row=1, max_rows=49):
        """List sales campaigns.
        Returns: {Total, CampaignItems: [{CampaignID, Date, Description, LastRunDate, Active, ...}]}
        """
        return self.sap.post("/webservices/SalesCampaignWs.asmx/GetSalesCampaignListItems", {
            "Input": {"activeTab": active_tab, "StartRow": start_row, "MaxRows": max_rows}
        })

    def get_campaign_tags(self):
        """Get all campaign tags (KLD has 159 tags).
        Returns: array of tag objects
        """
        return self.sap.post("/WebServices/SalesCampaignWs.asmx/GetAllCampaignTags", {})
