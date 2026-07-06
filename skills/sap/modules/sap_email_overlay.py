"""
sap_email_overlay.py — Email Overlay Operations
Endpoints: CRMBFF/EmailOverlay, CompanyBFF/EmailOverlay

Used to send emails from SAP to clients — estimates, invoices, bulk sends.
All endpoints confirmed cracked as of 2026-06-26.

KEY FINDINGS (from API map discovery):
- EmailOverlay_Estimate_SendEmail needs {"Input":{"EntityID":"<estimateGuid>"}}
- EmailOverlay_Estimate_CanEmail validates before sending: {"Input":{"IDs":["<guid>",...]}}
- EmailOverlay_GetEmailListByResource returns from-addresses for a resource
- EmailOverlay_GetStatusByTicket uses BARE {"TicketID":"<guid>"} (no wrapper)
- EmailOverlay_EstimateEmailDefaults_Get uses BARE {"EstimateID":"<guid>"}
- CompanyBFF/EmailOverlay handles invoice bulk email
"""
from .sap_core import SAPClient, get_sap, NULL_GUID


class EmailOverlayAPI:
    def __init__(self, sap=None):
        self.sap = sap or get_sap()

    # ─── ESTIMATES ────────────────────────────────────────────────────────────

    def can_email_estimates(self, estimate_ids):
        """Check which estimates can be emailed (validation step before send).
        estimate_ids: list of estimate GUIDs
        Returns: {ValidIDs: [...], ValidationMessages: [...]}
        """
        return self.sap.post("/CRMBFF/EmailOverlay/EmailOverlay_Estimate_CanEmail", {
            "Input": {"IDs": estimate_ids}
        })

    def get_estimate_defaults(self, estimate_id):
        """Get default email subject/body template for an estimate.
        Returns: {Subject, Body, Customer, Errors}
        NOTE: Uses BARE param (no Input wrapper).
        """
        return self.sap.post("/CRMBFF/EmailOverlay/EmailOverlay_EstimateEmailDefaults_Get", {
            "EstimateID": estimate_id
        })

    def send_estimate_email(self, estimate_id, subject=None, body=None, from_email=None, to_email=None):
        """Send a single estimate email to a client.
        estimate_id: estimate GUID
        subject/body: override defaults (optional — SAP will use template if None)
        from_email: sender address (use get_email_list_by_resource to get valid options)
        to_email: recipient address (optional — SAP uses client email on file)
        """
        payload = {"Input": {"EntityID": estimate_id}}
        if subject:
            payload["Input"]["Subject"] = subject
        if body:
            payload["Input"]["Body"] = body
        if from_email:
            payload["Input"]["FromEmail"] = from_email
        if to_email:
            payload["Input"]["ToEmail"] = to_email
        return self.sap.post("/CRMBFF/EmailOverlay/EmailOverlay_Estimate_SendEmail", payload)

    def send_bulk_estimate_email(self, estimate_ids):
        """Send bulk estimate emails to multiple clients.
        estimate_ids: list of estimate GUIDs
        NOTE: Call can_email_estimates() first to validate.
        """
        return self.sap.post("/CRMBFF/EmailOverlay/EmailOverlay_Estimate_SendBulkEmail", {
            "Input": {"IDs": estimate_ids}
        })

    # ─── INVOICES ─────────────────────────────────────────────────────────────

    def send_bulk_invoice_email(self, invoice_ids):
        """Send bulk invoice emails to multiple clients.
        invoice_ids: list of invoice GUIDs
        NOTE: Uses CompanyBFF (not CRMBFF) — different routing layer.
        """
        return self.sap.post("/CompanyBFF/EmailOverlay/EmailOverlay_Invoice_SendBulkEmail", {
            "Input": {"IDs": invoice_ids}
        })

    # ─── RESOURCE / FROM-ADDRESS ──────────────────────────────────────────────

    def get_email_list_by_resource(self, resource_id):
        """Get valid from-email addresses for a resource (employee).
        resource_id: employee GUID
        Returns: [{Text: "info@kootenaylawndoctor.com", Value: "info@..."}]
        KLD example: returns info@kootenaylawndoctor.com
        """
        return self.sap.post("/CRMBFF/EmailOverlay/EmailOverlay_GetEmailListByResource", {
            "Input": {"ResourceID": resource_id}
        })

    # ─── TICKET EMAIL STATUS ───────────────────────────────────────────────────

    def get_status_by_ticket(self, ticket_id):
        """Get email status for a ticket.
        Returns: {Status: N} where N is an integer status code.
        NOTE: Uses BARE param (no Input wrapper).
        """
        return self.sap.post("/CRMBFF/EmailOverlay/EmailOverlay_GetStatusByTicket", {
            "TicketID": ticket_id
        })

    # ─── HELPERS ─────────────────────────────────────────────────────────────

    def send_estimate_with_defaults(self, estimate_id, resource_id=None):
        """Full send flow: get defaults → validate → send.
        Returns (success: bool, result: dict)
        """
        from .sap_core import USER_ID

        # Step 1: validate
        can_send = self.can_email_estimates([estimate_id])
        valid_ids = can_send.get("ValidIDs", [])
        if estimate_id not in valid_ids:
            msgs = can_send.get("ValidationMessages", [])
            return False, {"error": "Estimate cannot be emailed", "messages": msgs}

        # Step 2: get from-address
        rid = resource_id or USER_ID
        from_options = self.get_email_list_by_resource(rid)
        from_email = None
        if isinstance(from_options, list) and from_options:
            from_email = from_options[0].get("Value")

        # Step 3: send
        result = self.send_estimate_email(estimate_id, from_email=from_email)
        errors = result.get("Errors") or []
        success = len(errors) == 0
        return success, result
