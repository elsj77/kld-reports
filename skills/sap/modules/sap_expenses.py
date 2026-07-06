"""sap_expenses.py — Expense Operations. Endpoints: ExpensesWs (13 ops, WSDL-confirmed)"""
from .sap_core import SAPClient, get_sap, NULL_GUID

class ExpensesAPI:
    def __init__(self, sap=None):
        self.sap = sap or get_sap()
    
    def query(self, start_row=1, max=22, filters=None):
        return self.sap.post("/AccountingBFF/ExpenseList/Query", {"QueryInput": {"StartRow": start_row, "Max": max, "ScreenViewFilterTypes": filters or [], "SortedColumns": []}})
    
    def query_by_ids(self, expense_ids):
        return self.sap.post("/AccountingBFF/ExpenseList/QueryByIDs", {"IDs": expense_ids})
    
    def delete(self, expense_ids):
        return self.sap.post("/WebServices/Accounting/ExpensesWs.asmx/DeleteExpenses", {"ExpenseIDs": expense_ids})
    
    def save(self, expense_data):
        return self.sap.post("/WebServices/Accounting/ExpensesWs.asmx/SaveExpense", expense_data)
    
    def export(self, export_data):
        return self.sap.post("/WebServices/Accounting/ExpensesWs.asmx/ExportExpenses", export_data)
    
    def get_line_items(self, expense_id):
        return self.sap.post("/WebServices/Accounting/ExpensesWs.asmx/GetExpenseLineItems", {"ExpenseID": expense_id})
    
    def get_class_by_service_type(self, service_type_id):
        return self.sap.post("/WebServices/Accounting/ExpensesWs.asmx/GetClassByServiceType", {"ServiceTypeID": service_type_id})
    
    def build_purchase_order(self, po_data):
        return self.sap.post("/WebServices/Accounting/ExpensesWs.asmx/BuildPurchaseOrderExpense", po_data)
