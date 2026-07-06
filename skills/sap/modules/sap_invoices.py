"""
sap_invoices.py — Invoice Operations
Endpoints: InvoicesWs (20+ ops), AccountingBFF/InvoiceList,
           InvoiceOverlay.asmx (7 ops), v3/InvoicesWs (5 ops)

INVOICEOVERLAY is the create/edit path — use it to build new invoices.
AccountingBFF/InvoiceList is the list/search/query path.
"""
from .sap_core import SAPClient, get_sap, NULL_GUID


class InvoicesAPI:
    def __init__(self, sap=None):
        self.sap = sap or get_sap()

    # ─── LIST / SEARCH ────────────────────────────────────────────────────────

    def query(self, start_row=1, max=22, filters=None, start_date=None, end_date=None):
        """Query invoice list with optional date range and filters."""
        no_date = {"Month": -1, "Day": -1, "Year": -1}
        return self.sap.post("/AccountingBFF/InvoiceList/Query", {
            "QueryInput": {
                "StartRow": start_row,
                "Max": max,
                "StartDate": start_date or no_date,
                "EndDate": end_date or no_date,
                "ActiveTab": "",
                "ScreenViewFilterTypes": filters or [],
                "SortedColumns": []
            }
        })

    def query_by_ids(self, invoice_ids):
        """Query specific invoices by GUID list."""
        return self.sap.post("/AccountingBFF/InvoiceList/QueryByIDs", {
            "IDs": invoice_ids
        })

    def query_totals(self, filters=None):
        """Get invoice list totals (count, amount owed, etc.)."""
        no_date = {"Month": -1, "Day": -1, "Year": -1}
        return self.sap.post("/AccountingBFF/InvoiceList/QueryTotals", {
            "QueryInput": {
                "StartRow": 1, "Max": 22,
                "StartDate": no_date, "EndDate": no_date,
                "ActiveTab": "",
                "ScreenViewFilterTypes": filters or [],
                "SortedColumns": []
            }
        })

    # ─── CREATE / EDIT (InvoiceOverlay) ──────────────────────────────────────

    def get_init_data(self):
        """Get invoice overlay initialization data.
        Returns: SalesTaxRefs, SalesTaxCodes, StandardTerms, ARAccounts
        Use this to populate dropdowns when building a new invoice.
        """
        return self.sap.post("/WebServices/InvoiceOverlay.asmx/GetInitializationData", {})

    def get_client_data_for_invoice(self, client_guid):
        """Get client billing data for invoice overlay."""
        return self.sap.post("/WebServices/InvoiceOverlay.asmx/GetCustomerData", {
            "CustomerID": client_guid
        })

    def get_client_billing_notes(self, client_guid):
        """Get billing notes shown in invoice overlay."""
        return self.sap.post("/WebServices/InvoiceOverlay.asmx/GetCustomerBillingNotes", {
            "CustomerID": client_guid
        })

    def get_sales_tax(self, client_guid):
        """Get sales tax rate for a client."""
        return self.sap.post("/WebServices/InvoiceOverlay.asmx/GetSalesTax", {
            "CustomerID": client_guid
        })

    def calculate_sales_tax(self, client_guid, subtotal):
        """Calculate tax amount for a given subtotal."""
        return self.sap.post("/WebServices/InvoiceOverlay.asmx/CalculateSalesTax", {
            "CustomerID": client_guid,
            "Subtotal": subtotal
        })

    def get_expenses_for_invoice(self, client_guid):
        """Get expense items available to add to an invoice."""
        return self.sap.post("/WebServices/InvoiceOverlay.asmx/GetExpenses", {
            "CustomerID": client_guid
        })

    def save(self, invoice_data):
        """Create or update an invoice via InvoiceOverlay.
        invoice_data: full invoice payload. Use get_init_data() + get_client_data_for_invoice()
                      to pre-populate required fields.
        NULL_GUID as InvoiceID = create new.
        Returns: {InvoiceID, InvoiceNumber, Errors}
        """
        return self.sap.post("/WebServices/InvoiceOverlay.asmx/SaveInvoice", invoice_data)

    def save_line_item_class(self, service_id, class_id):
        """Set QuickBooks class on an invoice line item."""
        return self.sap.post("/WebServices/InvoiceOverlay.asmx/SaveLineItemClass", {
            "Input": {"ServiceID": service_id, "ClassID": class_id}
        })

    # ─── STATUS OPERATIONS ────────────────────────────────────────────────────

    def delete(self, invoice_ids):
        """Delete invoices."""
        return self.sap.post("/WebServices/Accounting/InvoicesWs.asmx/DeleteInvoices", {
            "InvoiceIDs": invoice_ids
        })

    def restore(self, invoice_ids):
        """Restore deleted invoices."""
        return self.sap.post("/WebServices/Accounting/InvoicesWs.asmx/RestoreInvoices", {
            "InvoiceIDs": invoice_ids
        })

    def void(self, invoice_id, confirm="YES"):
        """Void an invoice. Requires 'YES' confirmation string."""
        return self.sap.post("/WebServices/ClientViewWs.asmx/VoidInvoice", {
            "InvoiceID": invoice_id,
            "ConfirmText": confirm
        })

    def lock(self, invoice_ids):
        """Lock invoices (prevent editing)."""
        return self.sap.post("/WebServices/Accounting/InvoicesWs.asmx/LockInvoices", {
            "InvoiceIDs": invoice_ids
        })

    def complete(self, invoice_ids):
        """Mark invoices as complete."""
        return self.sap.post("/WebServices/Accounting/InvoicesWs.asmx/CompleteInvoices", {
            "InvoiceIDs": invoice_ids
        })

    def mark_printed(self, invoice_ids):
        """Mark invoices as printed."""
        return self.sap.post("/WebServices/Accounting/InvoicesWs.asmx/MarkAsPrinted", {
            "InvoiceIDs": invoice_ids
        })

    def mail(self, invoice_ids):
        """Mail invoices."""
        return self.sap.post("/WebServices/Accounting/InvoicesWs.asmx/MailInvoices", {
            "InvoiceIDs": invoice_ids
        })

    def merge(self, invoice_ids):
        """Merge multiple invoices into one."""
        return self.sap.post("/WebServices/Accounting/InvoicesWs.asmx/MergeInvoices", {
            "InvoiceIDs": invoice_ids
        })

    def bulk_pay(self, invoice_data):
        """Bulk pay multiple invoices at once."""
        return self.sap.post("/WebServices/Accounting/InvoicesWs.asmx/BulkPayInvoices", invoice_data)

    def add_remove_other_charges(self, charge_data):
        """Add or remove other charges on an invoice (v3 endpoint)."""
        return self.sap.post("/v3/WebServices/Accounting/InvoicesWs.asmx/AddRemoveOtherCharges", charge_data)

    # ─── TERM LOOKUPS ─────────────────────────────────────────────────────────

    def get_term_days(self):
        """Get invoice term options (Net 15, Net 30, etc.)"""
        return self.sap.post("/v3/WebServices/Accounting/InvoicesWs.asmx/GetInvoiceTermDays", {})

    # ─── FROM ESTIMATE ────────────────────────────────────────────────────────

    def create_from_estimate(self, estimate_id, line_item_ids):
        """Create invoice from an estimate.
        estimate_id: estimate GUID (use field `ID` not `QuoteID`)
        line_item_ids: list of line item GUIDs to include
        NOTE: Requires real line item GUIDs — intercept from UI if unknown.
        Returns: {InvoiceID, Errors}
        """
        return self.sap.post("/webservices/QuoteWs.asmx/CreateInvoiceFromQuote", {
            "InputData": {"ID": estimate_id, "LineItemIDs": line_item_ids}
        })

    # ─── HELPERS ─────────────────────────────────────────────────────────────

    def get_outstanding(self, filters=None):
        """Get all outstanding (unpaid) invoices."""
        # Filter type for outstanding = ScreenViewFilterType for "Unpaid"
        return self.query(max=500, filters=filters)
