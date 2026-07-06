"""sap_forms.py — Form Operations. Endpoints: FormsWs, MarketingBFF/Form, Marketing/FormsWs (14 ops)"""
from .sap_core import SAPClient, get_sap, NULL_GUID

class FormsAPI:
    def __init__(self, sap=None):
        self.sap = sap or get_sap()
    
    def query(self, start_row=1, max=22, filters=None):
        return self.sap.post("/MarketingBFF/Form/Query", {"QueryInput": {"StartRow": start_row, "Max": max, "ActiveTab": "", "ScreenViewFilterTypes": filters or [], "SortedColumns": []}})
    
    def query_totals(self, filters=None):
        return self.sap.post("/MarketingBFF/Form/QueryTotals", {"QueryInput": {"StartRow": 1, "Max": 22, "ActiveTab": "", "ScreenViewFilterTypes": filters or [], "SortedColumns": []}})
    
    def query_form_data(self, form_id):
        return self.sap.post("/WebServices/FormsWs.asmx/QueryFormData", {"FormID": form_id})
    
    def get_response_options(self, form_id):
        return self.sap.post("/WebServices/FormsWs.asmx/GetFormResponseOptions", {"FormID": form_id})
    
    def process_form(self, form_data):
        return self.sap.post("/WebServices/FormsWs.asmx/ProcessFormCreateMethod", form_data)
    
    def get_full_forms_list(self):
        return self.sap.post("/MarketingBFF/Form/GetFullFormsList", {})
    
    def get_documents(self, form_id):
        return self.sap.post("/v3/WebServices/Marketing/FormsWs.asmx/GetDocuments", {"FormID": form_id})
    
    def get_account_type_mapping(self):
        return self.sap.post("/v3/WebServices/Marketing/FormsWs.asmx/GetAccountTypeMapping", {})
    
    def get_custom_fields_mapping(self):
        return self.sap.post("/v3/WebServices/Marketing/FormsWs.asmx/GetCustomFieldsForMapping", {})
    
    def get_tags(self):
        return self.sap.post("/v3/WebServices/Marketing/FormsWs.asmx/GetTags", {})
