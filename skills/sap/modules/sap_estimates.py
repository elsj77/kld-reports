"""
sap_estimates.py — Estimate/Quote CRUD Operations
Endpoints: QuoteWs (38 ops), CRMBFF/Estimate

CRACKED 2026-06-25: All major write endpoints confirmed working.
Key finding: SAP QuoteWs uses inconsistent field naming across endpoints.
- CopyEstimate, CreateInvoiceFromQuote: use `ID` (not `QuoteID`)
- MarkAsAcceptedOrDeclined, SetEstimateStatus, GetQuoteListLineItems: use `QuoteID`
- DeleteEstimates: uses `IDs` (array)
- ConvertLead: bare `CustomerID` param, no wrapper object
"""
import json
from datetime import datetime, timedelta
from .sap_core import SAPClient, get_sap, NULL_GUID


class EstimatesAPI:
    def __init__(self, sap=None):
        self.sap = sap or get_sap()

    # ─── READ ───────────────────────────────────────────────────────

    def query(self, estimate_id, customer_id=None):
        """Get full estimate data (shell + metadata, no line items)."""
        return self.sap.post("/webservices/QuoteWs.asmx/Query", {
            "InputData": {"ID": estimate_id, "CustomerID": customer_id or NULL_GUID}
        })

    def query_simple(self, estimate_id, customer_id=None):
        """Get simple estimate data including line items.
        Pass customer_id to get line items populated."""
        payload = {"InputData": {"ID": estimate_id}}
        if customer_id:
            payload["InputData"]["CustomerID"] = customer_id
        return self.sap.post("/webservices/QuoteWs.asmx/QuerySimple", payload)

    def query_line_items(self, estimate_id):
        """Get estimate line items via QuoteWs/QueryLineItems."""
        return self.sap.post("/webservices/QuoteWs.asmx/QueryLineItems", {
            "InputData": {"ID": estimate_id}
        })

    def get_line_items(self, estimate_id, customer_id):
        """Get line items for an estimate via GetQuoteListLineItems.
        Uses `QuoteID` + `CustomerID` in InputData wrapper."""
        return self.sap.post("/webservices/QuoteWs.asmx/GetQuoteListLineItems", {
            "InputData": {"QuoteID": estimate_id, "CustomerID": customer_id}
        })

    def search(self, start_row=1, max_rows=50, filters=None):
        """Search estimates via CRMBFF V2EstimateList_Query.
        Returns: {Estimates: [{ID, Number, ClientName, ClientID, QuoteStageName, QuoteStageType, EstimatedValue, QuoteDate, ...}]}
        NOTE: Field is `Number` not `EstimateNumber` in results. ClientID = customer GUID."""
        payload = {
            "QueryInput": {
                "ActiveTab": "Results",
                "StartRow": start_row,
                "Max": max_rows,
                "ScreenViewFilterTypes": filters or [],
                "SortedColumns": [{"FieldName": "EstimateNumber", "Direction": 1, "ColumnEnum": 11}]
            }
        }
        return self.sap.post("/CRMBFF/Estimate/V2EstimateList_Query", payload)

    def get_totals(self, filters=None):
        """Get estimate count via V2EstimateList_QueryTotals."""
        payload = {
            "QueryInput": {
                "ActiveTab": "Results",
                "StartRow": 1,
                "Max": 1,
                "ScreenViewFilterTypes": filters or [],
                "SortedColumns": []
            }
        }
        return self.sap.post("/CRMBFF/Estimate/V2EstimateList_QueryTotals", payload)

    def get_for_client(self, customer_job_id, only_recent=False, is_lead=False):
        """Get all estimates for a client via CRMBFF GetV2Estimates.
        customer_job_id: the client's CustomerJobID (from ClientViewWs/GetCustomerDataAsync).
        Returns: {Items: [{ID, Number, Description, QuoteStageName, EstimatedValue, EstimateEditorType, ...}]}
        EstimateEditorType=1 means V3 overlay."""
        return self.sap.post("/CRMBFF/Quote/GetV2Estimates", {
            "request": {
                "CustomerJobID": customer_job_id,
                "IsLead": is_lead,
                "OnlyRecent": only_recent
            }
        })

    def get_default_stage(self):
        """Get default quote stage."""
        return self.sap.post("/webservices/QuoteWs.asmx/GetDefaultQuoteStage", {})

    def get_default_sales_rep(self):
        """Get default sales rep for current user."""
        return self.sap.post("/webservices/QuoteWs.asmx/GetDefaultSalesRep", {})

    def get_service_matrix(self):
        """Get service matrix data (all services with rates)."""
        return self.sap.post("/webservices/QuoteWs.asmx/GetServiceMatrixData", {})

    def get_product_matrix(self):
        """Get product matrix data."""
        return self.sap.post("/webservices/QuoteWs.asmx/GetProductMatrixData", {})

    def get_permission_data(self, estimate_id):
        """Get estimate permissions. Uses `QuoteID`."""
        return self.sap.post("/webservices/QuoteWs.asmx/GetPermissionData", {
            "InputData": {"QuoteID": estimate_id}
        })

    def get_default_settings(self):
        """Get default estimate settings from CRMBFF."""
        return self.sap.post("/CRMBFF/EstimateEdit/CreateDefault_EstimateSettings", {})

    # ─── WRITE — CRACKED 2026-06-25 ────────────────────────────────

    def copy(self, estimate_id, customer_id, description=None, status="1"):
        """Copy an estimate.
        
        CRACKED 2026-06-25: Field is `ID` (NOT `QuoteID`).
        Wrapper: {"Data": {...}}
        
        Args:
            estimate_id: GUID of the source estimate to copy
            customer_id: GUID of the customer to copy TO
            description: New description (default: "Copy of #<num>")
            status: String from DOM status dropdown (default: "1" = Draft)
            
        Returns: CopyEstimateResponse{LineItemModel: {ID, Number, QuoteStageName, ...}}
                 LineItemModel.ID = new estimate GUID
                 LineItemModel.Number = new estimate number
        """
        desc = description or f"Copy of estimate {estimate_id[:8]}"
        return self.sap.post("/webservices/QuoteWs.asmx/CopyEstimate", {
            "Data": {
                "ID": estimate_id,
                "CustomerID": customer_id,
                "Description": desc,
                "status": str(status)
            }
        })

    def create_invoice(self, estimate_id, line_item_ids):
        """Create an invoice from an estimate.
        
        CRACKED 2026-06-25: Field is `ID` (NOT `QuoteID`).
        Wrapper: {"InputData": {...}}
        
        Args:
            estimate_id: GUID of the source estimate
            line_item_ids: List of line item GUIDs to include in invoice
            
        Returns: CreateInvoiceFromQuoteResponse{InvoiceID, Errors, CallStack}
                 InvoiceID = GUID of the newly created invoice
        """
        return self.sap.post("/webservices/QuoteWs.asmx/CreateInvoiceFromQuote", {
            "InputData": {
                "ID": estimate_id,
                "LineItemIDs": line_item_ids
            }
        })

    def convert_lead(self, customer_id):
        """Convert a lead to an active customer.
        
        CRACKED 2026-06-25: Bare `CustomerID` param — NO wrapper object.
        The JSON body is literally just {"CustomerID": "<guid>"}.
        
        Args:
            customer_id: GUID of the lead/customer to convert
            
        Returns: ConvertLeadResponse{LeadName, Errors, CallStack}
        """
        return self.sap.post("/webservices/QuoteWs.asmx/ConvertLead", {
            "CustomerID": customer_id
        })

    def delete(self, estimate_ids):
        """Delete one or more estimates.
        
        CRACKED 2026-06-25: Field is `IDs` (NOT `EstimateIDs`).
        Wrapper: {"Data": {...}}
        
        Args:
            estimate_ids: Single GUID or list of GUIDs to delete
            
        Returns: DeleteEstimatesResponse{Ids: [deleted_guids], Errors, CallStack}
        """
        if isinstance(estimate_ids, str):
            estimate_ids = [estimate_ids]
        return self.sap.post("/webservices/QuoteWs.asmx/DeleteEstimates", {
            "Data": {"IDs": estimate_ids}
        })

    def mark_accepted(self, estimate_id, status=1):
        """Mark estimate as accepted (Won) or declined.
        
        CRACKED 2026-06-25: Uses `QuoteID` (NOT `ID` here — inconsistent with Copy!).
        Wrapper: {"InputData": {...}}
        Status is an int: 1=Won/Accepted.
        
        Args:
            estimate_id: GUID of the estimate
            status: 1=Won/Accepted (default), other values for declined/etc.
            
        Returns: MarkAsAcceptedOrDeclinedResponse{Errors, CallStack}
        """
        return self.sap.post("/webservices/QuoteWs.asmx/MarkAsAcceptedOrDeclined", {
            "InputData": {"QuoteID": estimate_id, "Status": status}
        })

    def set_status(self, estimate_id, stage_id):
        """Set estimate stage/status.
        
        Uses `QuoteID` + `StageID` in `Data` wrapper.
        
        Args:
            estimate_id: GUID of the estimate
            stage_id: GUID of the stage (e.g. Draft, Won, Lost, Quote)
            
        Returns: status change result
        """
        return self.sap.post("/webservices/QuoteWs.asmx/SetEstimateStatus", {
            "Data": {"QuoteID": estimate_id, "StageID": stage_id}
        })

    def update_stage_batch(self, estimate_ids, stage_id):
        """Update stage for multiple estimates at once.
        
        Uses `QuoteIDs` (array) + `StageID` in `InputData` wrapper.
        
        Args:
            estimate_ids: List of estimate GUIDs
            stage_id: GUID of the target stage
            
        Returns: batch update result
        """
        if isinstance(estimate_ids, str):
            estimate_ids = [estimate_ids]
        return self.sap.post("/webservices/QuoteWs.asmx/UpdateStageForQuotes", {
            "InputData": {"QuoteIDs": estimate_ids, "StageID": stage_id}
        })

    # ─── WRITE — EXISTING (Save/Add) ───────────────────────────────

    def save(self, estimate_data):
        """Save full estimate (create/update) via QuoteWs/Save."""
        return self.sap.post("/webservices/QuoteWs.asmx/Save", estimate_data)

    def save_simple(self, estimate_data):
        """Save simple estimate via QuoteWs/SaveSimple."""
        return self.sap.post("/webservices/QuoteWs.asmx/SaveSimple", estimate_data)

    def add_service(self, quote_id, service_data):
        """Add a service line item to an existing estimate."""
        return self.sap.post("/webservices/QuoteWs.asmx/AddService", {
            "InputData": {"QuoteID": quote_id, "ServiceData": service_data}
        })

    def add_package(self, quote_id, package_data):
        """Add a package to an existing estimate."""
        return self.sap.post("/webservices/QuoteWs.asmx/AddPackage", {
            "InputData": {"QuoteID": quote_id, "PackageData": package_data}
        })

    def add_product(self, quote_id, product_data):
        """Add a product line item to an existing estimate."""
        return self.sap.post("/webservices/QuoteWs.asmx/AddProduct", {
            "InputData": {"QuoteID": quote_id, "ProductData": product_data}
        })

    def preview(self, estimate_id):
        """Preview estimate (generate preview document)."""
        return self.sap.post("/webservices/QuoteWs.asmx/PreviewQuote", {
            "InputData": {"QuoteID": estimate_id}
        })

    # ─── BUILDERS (payload construction helpers) ───────────────────

    def build_estimate(self, client_guid, description=None, stage="draft",
                       service_line_items=None, quote_id=None, valid_from=None,
                       valid_to=None, sales_rep_id=None, source_id=None,
                       po_number="", work_order_number="", installments="1",
                       notes_tab="", show_discount=False):
        """
        Build a full InputData payload for QuoteWs.asmx/Save.
        For new estimate: omit quote_id. For updating: pass existing estimate GUID.
        stage: "draft", "sent", "won", "lost", "contract", "renewal", etc.
        service_line_items: list of build_service_item() or build_package_item() results.
        """
        from sap_create_estimate import build_estimate_payload
        return build_estimate_payload(
            client_guid, description, stage, service_line_items, quote_id,
            valid_from, valid_to, sales_rep_id, source_id, None,
            work_order_number, po_number, installments, notes_tab, show_discount
        )

    def build_service_item(self, service_type_id, rate, qty=1, visits=1, bhrs="0.50",
                           estimate_note="", route_note="", invoice_note="",
                           item_note="", status_enum=4, display_order=0, start_date=None):
        """Build a single service line item payload for an estimate."""
        from sap_create_estimate import build_service_item
        return build_service_item(service_type_id, rate, qty, visits, bhrs,
                                  estimate_note, route_note, invoice_note,
                                  item_note, status_enum, None, display_order, start_date)

    def build_package_item(self, package_id, subservices, estimate_note="",
                           route_note="", invoice_note="", status_enum=4, display_order=0):
        """Build a package line item payload for an estimate."""
        from sap_create_estimate import build_package_item
        return build_package_item(package_id, subservices, estimate_note,
                                  route_note, invoice_note, status_enum, None, display_order)

    def create(self, client_guid, description=None, stage="draft", service_line_items=None, **kwargs):
        """One-shot: build + save an estimate. Returns the save result."""
        payload = self.build_estimate(client_guid, description, stage, service_line_items, **kwargs)
        return self.save(payload)

    # ─── HIGH-LEVEL WORKFLOWS ──────────────────────────────────────

    def copy_estimate_to_client(self, source_estimate_id, target_customer_id, description=None):
        """Copy an estimate to a different client and return the new estimate ID.
        
        High-level wrapper around copy() that extracts the new estimate GUID.
        
        Returns: (new_estimate_id, new_estimate_number) or (None, None) on failure
        """
        result = self.copy(source_estimate_id, target_customer_id, description)
        if isinstance(result, dict):
            line_item = result.get("LineItemModel", {})
            new_id = line_item.get("ID")
            new_num = line_item.get("Number")
            if new_id:
                return new_id, new_num
        return None, None

    def invoice_from_estimate(self, estimate_id, customer_id):
        """Create an invoice from an estimate, auto-fetching line items.
        
        High-level workflow:
        1. Get line items for the estimate
        2. Create invoice from those line items
        
        Returns: invoice_id (GUID) or None on failure
        """
        # Get line items
        li_result = self.query_simple(estimate_id, customer_id)
        line_items = []
        if isinstance(li_result, dict):
            line_items = li_result.get("LineItems", [])
        
        if not line_items:
            # Fallback: try GetQuoteListLineItems
            li_result2 = self.get_line_items(estimate_id, customer_id)
            if isinstance(li_result2, list):
                line_items = li_result2
            elif isinstance(li_result2, dict):
                line_items = li_result2.get("Items", li_result2.get("d", []))
        
        li_ids = [li.get("ID") for li in line_items if isinstance(li, dict) and li.get("ID")]
        
        if not li_ids:
            return None, "No line items found for estimate"
        
        result = self.create_invoice(estimate_id, li_ids)
        if isinstance(result, dict):
            invoice_id = result.get("InvoiceID")
            errors = result.get("Errors", [])
            if invoice_id and not errors:
                return invoice_id, None
            elif errors:
                return None, "; ".join(str(e) for e in errors)
        
        return None, "Unexpected response from CreateInvoiceFromQuote"

    def won_estimate_to_invoice(self, estimate_id, customer_id):
        """Full workflow: ensure estimate is Won, then create invoice.
        
        1. Mark estimate as Won (Status=1)
        2. Create invoice from estimate line items
        
        Returns: (invoice_id, error) tuple
        """
        # Step 1: Mark as Won
        self.mark_accepted(estimate_id, status=1)
        
        # Step 2: Create invoice
        return self.invoice_from_estimate(estimate_id, customer_id)
