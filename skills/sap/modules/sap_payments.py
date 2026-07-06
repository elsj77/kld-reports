"""
sap_payments.py — Payment Operations
Endpoints: PaymentsWs, AccountingBFF/PaymentList, PaymentOverlayWs

BILLING PROTECTION:
  GetBillingInformation returns stored card/ACH data — READ ONLY.
  NEVER write CC/payment method data back via SavePaymentData.
  SavePaymentData is for recording cash/cheque/e-transfer payments only.

SavePaymentData payload shape (confirmed 2026-05-19):
  Amount, PaymentDate{M,D,Y}, PaymentMethodID, CheckNumber, Notes,
  CustomerID, InvoicePayments:[{InvoiceID, Amount}]
"""
from .sap_core import SAPClient, get_sap, NULL_GUID


class PaymentsAPI:
    def __init__(self, sap=None):
        self.sap = sap or get_sap()

    # ─── LIST / SEARCH ────────────────────────────────────────────────────────

    def query(self, start_row=1, max=22, filters=None):
        """Query payment list."""
        return self.sap.post("/AccountingBFF/PaymentList/Query", {
            "QueryInput": {
                "StartRow": start_row,
                "Max": max,
                "ScreenViewFilterTypes": filters or [],
                "SortedColumns": []
            }
        })

    def query_by_ids(self, payment_ids):
        """Query specific payments by GUID list."""
        return self.sap.post("/AccountingBFF/PaymentList/QueryByIDs", {
            "IDs": payment_ids
        })

    def query_totals(self, filters=None):
        """Get payment list totals."""
        return self.sap.post("/AccountingBFF/PaymentList/QueryTotals", {
            "QueryInput": {
                "StartRow": 1, "Max": 1,
                "ScreenViewFilterTypes": filters or [],
                "SortedColumns": []
            }
        })

    def get_applied_items(self, payment_id):
        """Get which invoices a payment has been applied to.
        Returns: [{InvoiceID, InvoiceNumber, Amount, ...}]
        """
        return self.sap.post("/AccountingBFF/PaymentList/GetAppliedPaymentItems", {
            "PaymentID": payment_id
        })

    # ─── OVERLAY — CLIENT DATA & INVOICE LOOKUP ───────────────────────────────

    def get_client_data(self, client_guid):
        """Get client data for payment overlay (name, balance, etc.)."""
        return self.sap.post("/WebServices/PaymentOverlayWs.asmx/GetCustomerData", {
            "CustomerID": client_guid
        })

    def get_billing_info(self, client_guid):
        """Get client billing information.
        BILLING PROTECTION: Returns stored payment method data — READ ONLY.
        Never write these values back.
        """
        return self.sap.post("/WebServices/PaymentOverlayWs.asmx/GetBillingInformation", {
            "CustomerID": client_guid
        })

    def get_outstanding_invoices(self, client_guid):
        """Get outstanding invoices available to apply a payment to.
        Returns: [{InvoiceID, InvoiceNumber, Balance, DueDate, ...}]
        """
        return self.sap.post("/WebServices/PaymentOverlayWs.asmx/GetInvoiceData", {
            "CustomerID": client_guid
        })

    def get_payment_methods(self):
        """Get available payment method options.
        KLD methods: Cash, Cheque, E-Transfer, Visa, MasterCard, AmEx, EFT, etc.
        Use KLD payment method GUIDs from sap_static_ids rule.
        """
        return self.sap.post("/WebServices/PaymentOverlayWs.asmx/GetPaymentMethod", {})

    def get_payment(self, payment_id):
        """Load an existing payment record for editing."""
        return self.sap.post("/WebServices/PaymentOverlayWs.asmx/GetPaymentData", {
            "PaymentID": payment_id
        })

    # ─── SAVE / VOID ─────────────────────────────────────────────────────────

    def save(self, payment_data):
        """Record a payment (cash/cheque/e-transfer/non-card).
        payment_data shape:
          {
            "Amount": 100.00,
            "PaymentDate": {"Month": 6, "Day": 26, "Year": 2026},
            "PaymentMethodID": "<guid>",   # from get_payment_methods() or static IDs
            "CheckNumber": "",
            "Notes": "",
            "CustomerID": "<client-guid>",
            "InvoicePayments": [{"InvoiceID": "<guid>", "Amount": 100.00}]
          }
        BILLING PROTECTION: Do not include CC fields.
        Returns: {Errors: [], PaymentID: "<guid>"}
        """
        return self.sap.post("/WebServices/PaymentOverlayWs.asmx/SavePaymentData", {
            "Data": payment_data
        })

    def void(self, payment_id):
        """Void a payment."""
        return self.sap.post("/WebServices/PaymentOverlayWs.asmx/VoidPayment", {
            "PaymentID": payment_id
        })

    # ─── BULK OPERATIONS ─────────────────────────────────────────────────────

    def delete(self, payment_ids):
        """Delete payments."""
        return self.sap.post("/WebServices/Accounting/PaymentsWs.asmx/DeletePayments", {
            "PaymentIDs": payment_ids
        })

    def restore(self, payment_ids):
        """Restore deleted payments."""
        return self.sap.post("/WebServices/Accounting/PaymentsWs.asmx/RestorePayments", {
            "PaymentIDs": payment_ids
        })

    # ─── HELPERS ─────────────────────────────────────────────────────────────

    def record_etransfer(self, client_guid, amount, invoice_id, notes="", check_number=""):
        """Shortcut: record an e-transfer payment against a single invoice.
        Uses KLD E-Transfer payment method GUID.
        """
        import datetime
        from .sap_core import NULL_GUID
        # KLD E-Transfer GUID from static IDs
        ETRANSFER_ID = "c3364b94-5bc6-48d7-914b-f2d6b5db6b72"
        today = datetime.date.today()
        return self.save({
            "Amount": amount,
            "PaymentDate": {"Month": today.month, "Day": today.day, "Year": today.year},
            "PaymentMethodID": ETRANSFER_ID,
            "CheckNumber": check_number,
            "Notes": notes,
            "CustomerID": client_guid,
            "InvoicePayments": [{"InvoiceID": invoice_id, "Amount": amount}]
        })

    def record_cheque(self, client_guid, amount, invoice_id, check_number="", notes=""):
        """Shortcut: record a cheque payment against a single invoice."""
        import datetime
        CHEQUE_ID = "e6988a0f-ee5d-4e1c-b095-ddf34f342404"
        today = datetime.date.today()
        return self.save({
            "Amount": amount,
            "PaymentDate": {"Month": today.month, "Day": today.day, "Year": today.year},
            "PaymentMethodID": CHEQUE_ID,
            "CheckNumber": check_number,
            "Notes": notes,
            "CustomerID": client_guid,
            "InvoicePayments": [{"InvoiceID": invoice_id, "Amount": amount}]
        })
