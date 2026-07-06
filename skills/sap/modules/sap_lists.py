"""
sap_lists.py — Lookup List Operations
Endpoints: ListsWs (20+ ops) — service types, schedules, divisions, taxes,
           payment methods, resources, crews, custom field lists

These are the "reference data" endpoints. Results are mostly stable and
can be cached. The heavy hitters (resources, service types) are already
documented in the SAP Static ID Reference rule.
"""
from .sap_core import SAPClient, get_sap, NULL_GUID, COMPANY_ID


class ListsAPI:
    def __init__(self, sap=None):
        self.sap = sap or get_sap()

    # ─── RESOURCES & CREWS ───────────────────────────────────────────────────

    def get_resources(self):
        """Get all resources (employees + crews/trucks).
        Returns: [{ResourceID, ResourceName, ResourceCode, ResourceType, ...}]
        KLD resource GUIDs are documented in the SAP Static ID Reference rule.
        """
        return self.sap.post("/WebServices/ListsWs.asmx/GetMoveToResourceList", {
            "CompanyID": COMPANY_ID
        })

    def get_crew_list(self):
        """Get crew list for dispatch board dropdown."""
        return self.sap.post("/WebServices/ListsWs.asmx/GetCrewList", {
            "CompanyID": COMPANY_ID
        })

    def get_resource_dropdown(self):
        """Get resource list in dropdown format."""
        return self.sap.post("/WebServices/ListsWs.asmx/GetResourceListForDropDown", {
            "CompanyID": COMPANY_ID
        })

    # ─── SERVICE TYPES ────────────────────────────────────────────────────────

    def get_service_types(self):
        """Get all service types.
        Returns: [{ServiceTypeID, ServiceTypeName, ServiceTypeCode, ...}]
        """
        return self.sap.post("/WebServices/ListsWs.asmx/GetServiceTypeList", {
            "CompanyID": COMPANY_ID
        })

    def get_service_type_dropdown(self):
        """Get service types in dropdown format for job creation."""
        return self.sap.post("/WebServices/ListsWs.asmx/GetServiceTypeDropDownList", {
            "CompanyID": COMPANY_ID
        })

    # ─── SCHEDULES ────────────────────────────────────────────────────────────

    def get_schedules(self):
        """Get all recurring schedule options (Weekly, Bi-weekly, Monthly, etc.)
        Returns: [{ScheduleID, ScheduleDescription, ...}]
        Required for SaveRecurringService payload.
        """
        return self.sap.post("/WebServices/ListsWs.asmx/GetScheduleList", {
            "CompanyID": COMPANY_ID
        })

    # ─── DIVISIONS ────────────────────────────────────────────────────────────

    def get_divisions(self):
        """Get all divisions.
        KLD divisions: KLD Inc., Blue Spruce, Mow and Snow — GUIDs in static IDs rule.
        """
        return self.sap.post("/WebServices/ListsWs.asmx/GetDivisionList", {
            "CompanyID": COMPANY_ID
        })

    # ─── TAXES ────────────────────────────────────────────────────────────────

    def get_sales_tax_codes(self):
        """Get sales tax code list."""
        return self.sap.post("/WebServices/ListsWs.asmx/GetSalesTaxCodeList", {
            "CompanyID": COMPANY_ID
        })

    def get_sales_tax_refs(self):
        """Get sales tax reference list."""
        return self.sap.post("/WebServices/ListsWs.asmx/GetSalesTaxRefList", {
            "CompanyID": COMPANY_ID
        })

    # ─── PAYMENT ─────────────────────────────────────────────────────────────

    def get_payment_methods(self):
        """Get all payment methods.
        KLD method GUIDs are documented in the SAP Static ID Reference rule.
        Returns: [{PaymentMethodID, Name, ...}]
        """
        return self.sap.post("/WebServices/ListsWs.asmx/GetPaymentMethods", {
            "CompanyID": COMPANY_ID
        })

    def get_standard_terms(self):
        """Get invoice standard terms (Net 15, Net 30, Due on Receipt, etc.)"""
        return self.sap.post("/WebServices/ListsWs.asmx/GetStandardTermList", {
            "CompanyID": COMPANY_ID
        })

    # ─── TAGS ─────────────────────────────────────────────────────────────────

    def get_available_tags(self, entity_type=1):
        """Get all available tags for an entity type.
        entity_type: 1=Client, 2=Job
        """
        return self.sap.post("/webservices/ListsWs.asmx/GetAvailableTagsList", {
            "InputData": {"EntityType": entity_type}
        })

    # ─── CUSTOM FIELDS ────────────────────────────────────────────────────────

    def get_custom_field_list(self):
        """Get company custom field definitions.
        KLD custom field GUIDs are documented in the SAP Static ID Reference rule.
        """
        return self.sap.post("/WebServices/ListsWs.asmx/GetCustomFieldList", {
            "CompanyID": COMPANY_ID
        })

    # ─── MAP CODES ────────────────────────────────────────────────────────────

    def get_map_codes(self):
        """Get all map codes (routing zones)."""
        return self.sap.post("/WebServices/ListsWs.asmx/GetMapCodeList", {
            "CompanyID": COMPANY_ID
        })

    # ─── STATES / COUNTRIES ──────────────────────────────────────────────────

    def get_states(self, country_id=None):
        """Get state/province list.
        BC StateID: 235cc50f-dc1c-4571-80ec-04050eb615e8
        """
        payload = {}
        if country_id:
            payload["CountryID"] = country_id
        return self.sap.post("/WebServices/ListsWs.asmx/GetStateList", payload)

    def get_countries(self):
        """Get country list.
        Canada CountryID: 9d09a286-14ac-4661-ad8f-d8984ef3e6b6
        """
        return self.sap.post("/WebServices/ListsWs.asmx/GetCountryList", {})

    # ─── INVOICE FREQUENCY ────────────────────────────────────────────────────

    def get_invoice_frequencies(self):
        """Get invoice frequency options (Per Visit, Monthly, etc.)"""
        return self.sap.post("/WebServices/ListsWs.asmx/GetInvoiceFrequencyList", {
            "CompanyID": COMPANY_ID
        })

    # ─── SCREEN VIEWS ─────────────────────────────────────────────────────────

    def get_screen_views(self, screen_view_type=1):
        """Get screen views by type.
        screen_view_type: 1=Dispatch, 9=Calendar, etc.
        """
        return self.sap.post("/WebServices/ScreenViewWs.asmx/GetScreenViews", {
            "InputData": {"ScreenViewTypeValue": screen_view_type}
        })
