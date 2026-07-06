"""sap_credits.py — Credit/Memo Operations. Endpoints: CreditsWs (18 ops, WSDL-confirmed)"""
from .sap_core import SAPClient, get_sap, NULL_GUID

class CreditsAPI:
    def __init__(self, sap=None):
        self.sap = sap or get_sap()
    
    def query(self, start_row=1, max=22, filters=None):
        return self.sap.post("/AccountingBFF/CreditList/Query", {"QueryInput": {"StartRow": start_row, "Max": max, "ScreenViewFilterTypes": filters or [], "SortedColumns": []}})
    
    def query_by_ids(self, credit_ids):
        return self.sap.post("/AccountingBFF/CreditList/QueryByIDs", {"IDs": credit_ids})
    
    def delete(self, credit_ids):
        return self.sap.post("/WebServices/Accounting/CreditsWs.asmx/DeleteCredits", {"CreditIDs": credit_ids})
    
    def restore(self, credit_ids):
        return self.sap.post("/WebServices/Accounting/CreditsWs.asmx/RestoreCredits", {"CreditIDs": credit_ids})
    
    def get_invoice_credit_items(self, invoice_id):
        return self.sap.post("/WebServices/Accounting/CreditsWs.asmx/GetInvoiceCreditItems", {"InvoiceID": invoice_id})
    
    def get_credit_line_items(self, credit_id):
        return self.sap.post("/WebServices/Accounting/CreditsWs.asmx/GetCreditLineItems", {"CreditID": credit_id})
    
    def get_service_product_details(self, credit_id):
        return self.sap.post("/WebServices/Accounting/CreditsWs.asmx/GetServiceProductDetails", {"CreditID": credit_id})
    
    def get_tax_amount(self, tax_data):
        return self.sap.post("/WebServices/Accounting/CreditsWs.asmx/GetCreditTaxAmount", tax_data)
