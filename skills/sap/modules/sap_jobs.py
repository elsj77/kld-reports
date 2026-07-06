"""
sap_jobs.py — Job/Service CRUD Operations
Endpoints: ServiceEditorWs (OneTime, Recurring, Package), SnowEditorWs (OnDemand/Snow)

CRITICAL DISTINCTIONS:
- OneTime: ServiceEditorWs.asmx/SaveOneTimeService, wrapper {"Input": {...}}, uses ServiceDetails[{Detail:{}}]
- Recurring: ServiceEditorWs.asmx/SaveRecurringService, wrapper {"Input": {...}}, uses Service.Details[] (FLAT)
- OnDemand/Snow: SnowEditorWs.asmx/Save, wrapper {"InputData": {...}}, uses sub-models
- Package: ServiceEditorWs.asmx/SavePackage, wrapper {"Input": {...}}, uses ServiceDetails[{Detail:{}}]

⚠️ Do NOT use ServiceEditorWs.asmx/SaveOnDemandService — architecturally broken. Use SnowEditorWs.asmx/Save.
"""
from .sap_core import SAPClient, get_sap, NULL_GUID, EMPTY_GUID, USER_ID, JOB_ID
import datetime

class JobsAPI:
    def __init__(self, sap=None):
        self.sap = sap or get_sap()
    
    # ─── One Time Jobs ───
    def save_one_time(self, payload):
        """Save a one-time job. Uses ServiceDetails[{Detail:{}}] structure."""
        return self.sap.post("/WebServices/ServiceEditorWs.asmx/SaveOneTimeService", {"Input": payload})
    
    # ─── Recurring Jobs (Mowing, Fertilizer, etc.) ───
    def save_recurring(self, payload):
        """
        Save a recurring job. Uses Service.Details[] (FLAT array, NOT nested Detail key).
        Required: JobType (1=Weekly, 2=Monthly), Timing="Recurring", ScheduleID, ScheduleDescription
        Each detail needs InitialDate. EndDate must be valid. Uses InvoiceFrequency.
        """
        return self.sap.post("/WebServices/ServiceEditorWs.asmx/SaveRecurringService", {"Input": payload})
    
    # ─── OnDemand/Snow Jobs ───
    def save_on_demand(self, payload):
        """
        Save an OnDemand/Snow job via SnowEditorWs.asmx/Save (NOT ServiceEditorWs).
        Wrapper is {"InputData": {...}}. Structure: JobInfoModel, InvoiceSetupModel, 
        RateMatrixModel, DetailsModel, NotesModel, ProductsModel.
        DiscountExpiration must be null. InvoiceTypeEnum: 1=FlatRate, 0=Contract.
        """
        return self.sap.post("/webservices/SnowEditorWs.asmx/Save", {"InputData": payload})
    
    # ─── Package Jobs ───
    def save_package(self, payload):
        """Save/create a package job. Uses ServiceDetails[{Detail:{}}] structure."""
        return self.sap.post("/WebServices/ServiceEditorWs.asmx/SavePackage", {"Input": payload})
    
    # ─── Other Job Types ───
    def save_custom_recurring(self, payload):
        return self.sap.post("/WebServices/ServiceEditorWs.asmx/SaveCustomRecurringService", {"Input": payload})
    
    def save_waiting_list(self, payload):
        return self.sap.post("/WebServices/ServiceEditorWs.asmx/SaveWaitingListService", {"Input": payload})
    
    def save_monthly(self, payload):
        return self.sap.post("/WebServices/ServiceEditorWs.asmx/SaveMonthlyService", {"Input": payload})
    
    # ─── Job Editor Resources ───
    def get_editor_resources(self):
        return self.sap.post("/WebServices/ServiceEditorWs.asmx/GetEditorDialogResources", {})
    
    def get_package_service_list(self, package_template_id):
        return self.sap.post("/WebServices/ServiceEditorWs.asmx/GetPackageServiceListData", {"PackageID": package_template_id})
    
    def get_service_total(self, payload):
        return self.sap.post("/WebServices/ServiceEditorWs.asmx/GetServiceTotal", payload)
    
    def get_recurring_calendar_dates(self, payload):
        return self.sap.post("/WebServices/ServiceEditorWs.asmx/GetRecurringCalendarDates", payload)
    
    # ─── Snow Editor Resources ───
    def get_snow_panel(self, service_id=NULL_GUID, customer_id=NULL_GUID, quote_line_item_id=NULL_GUID):
        """Load Snow/OnDemand panel data for initialization."""
        return self.sap.post("/webservices/SnowEditorWs.asmx/Query", {
            "InputData": {"ID": service_id, "CustomerID": customer_id, "QuoteLineItemID": quote_line_item_id}
        })
    
    def get_snow_crew_list(self):
        return self.sap.post("/webservices/SnowEditorWs.asmx/GetCrewEEVendorList", {})
    
    # ─── Quote -> Job Conversion ───
    # NOTE 2026-06-25: CreatePackageJobFromQuote and CreateRecurringJobFromQuote
    # do NOT exist as QuoteWs.asmx or ServiceEditorWs.asmx endpoints (confirmed 404).
    # The UI "Schedule" button (scheduleBtnClick in Estimates.js) triggers job creation
    # through ScheduledWorkWs.asmx/Save or ServiceEditorWs.asmx/Save with the quote
    # line item data embedded in the save payload.
    # Use build_onetime_payload / build_recurring_payload + save_one_time / save_recurring
    # to create jobs from estimate line items programmatically.
    def create_job_from_quote(self, quote_id, customer_id, line_item_id=None, job_type="Package"):
        """Create a job from a quote line item.
        
        DEPRECATED: The dedicated Quote->Job endpoints (CreatePackageJobFromQuote,
        CreateRecurringJobFromQuote) do NOT exist in SAP's API surface.
        
        Instead, use the build_*_payload + save_* methods:
        1. Get estimate line items via estimates.query_simple(quote_id, customer_id)
        2. Extract service_type_id, rate, qty from the line item
        3. Build a job payload via build_onetime_payload() or build_recurring_payload()
        4. Save via save_one_time() or save_recurring()
        """
        raise NotImplementedError(
            "Quote->Job conversion endpoints do not exist in SAP API. "
            "Use build_onetime_payload/build_recurring_payload + save_one_time/save_recurring "
            "with data extracted from the estimate line items."
        )
    
    # ─── Service Notes & Details ───
    def get_service_notes(self, service_guid):
        return self.sap.post("/WebServices/ServiceEditorWs.asmx/GetServiceNotes", {"ServiceID": service_guid})
    
    def remove_service_detail(self, detail_guid):
        return self.sap.post("/WebServices/ServiceEditorWs.asmx/RemoveServiceDetail", {"DetailID": detail_guid})
    
    # ─── Convenience Builders ───
    def build_onetime_payload(self, client_guid, service_type_id, service_name, rate,
                              scheduled_date, hours=0.5, user_id=USER_ID, job_id=JOB_ID, **kwargs):
        """Build a complete OneTime save payload. scheduled_date: {Year, Month, Day}"""
        return _build_one_time_payload(client_guid, service_type_id, service_name, rate,
                                       scheduled_date, hours, user_id, job_id, **kwargs)
    
    def build_recurring_payload(self, client_guid, service_type_id, service_name, rate,
                                start_date, end_date, schedule_id, schedule_description,
                                days=None, hours=0.5, user_id=USER_ID, job_id=JOB_ID, **kwargs):
        """
        Build a complete Recurring save payload.
        start_date, end_date: {Year, Month, Day}
        schedule_id: GUID from ListsWs/GetScheduleList
        schedule_description: e.g. "Weekly - Friday"
        days: dict {mon: True, tue: True, ...} (default: Mon-Fri)
        """
        return _build_recurring_payload(client_guid, service_type_id, service_name, rate,
                                        start_date, end_date, schedule_id, schedule_description,
                                        days, hours, user_id, job_id, **kwargs)
    
    def build_on_demand_payload(self, client_guid, service_type_id, service_name, rate,
                                budgeted_hours=1, invoice_type=1, **kwargs):
        """
        Build a complete OnDemand/Snow save payload.
        invoice_type: 1=FlatRate (default), 0=Contract
        """
        return _build_on_demand_payload(client_guid, service_type_id, service_name, rate,
                                        budgeted_hours, invoice_type, **kwargs)


    def build_waiting_list_payload(self, client_guid, service_type_id, service_name, rate,
                              start_date, complete_by_date, hours=0.5, user_id=USER_ID, job_id=JOB_ID, **kwargs):
        """
        Build a complete Waiting List save payload.
        start_date: {Year, Month, Day} — when service can start
        complete_by_date: {Year, Month, Day} — deadline (required, must be valid)
        Uses ServiceDetails[{Detail:{}}] like OneTime, plus renewal fields.
        """
        return _build_waiting_list_payload(client_guid, service_type_id, service_name, rate,
                                           start_date, complete_by_date, hours, user_id, job_id, **kwargs)

    def build_package_payload(self, client_guid, selected_package_id, services,
                              user_id=USER_ID, job_id=JOB_ID, **kwargs):
        """
        Build a SavePackage payload (completely different structure from other job types).
        
        selected_package_id: package template GUID from GetPackagesList
        services: list of dicts, each with: Description, Rate, Quantity, Hours, etc.
                 Use build_package_service() to create each entry.
        """
        return _build_package_payload(client_guid, selected_package_id, services,
                                      user_id, job_id, **kwargs)




# ═══════════════════════════════════════════════════════════════════════
# PAYLOAD BUILDERS
# ═══════════════════════════════════════════════════════════════════════

def _browser_date(d):
    """Convert dict {Year, Month, Day} or string 'YYYY-MM-DD' to SAP BrowserDate."""
    if d is None:
        return None
    if isinstance(d, str):
        parts = d.split('-')
        d = {'Year': int(parts[0]), 'Month': int(parts[1]), 'Day': int(parts[2])}
    return {'Month': d['Month'], 'Day': d['Day'], 'Year': d['Year']}


def _build_one_time_payload(client_guid, service_type_id, service_name, rate,
                            scheduled_date, hours=0.5, user_id=USER_ID, job_id=JOB_ID, **kwargs):
    """Build a SaveOneTimeService payload."""
    sd = _browser_date(scheduled_date)
    return {
        "UserID": user_id, "JobID": job_id, "CustomerID": client_guid,
        "CustomerSourceID": kwargs.get("source_id", NULL_GUID),
        "ContractID": kwargs.get("contract_id", NULL_GUID),
        "ServiceID": NULL_GUID,
        "SalesPersonID": kwargs.get("sales_person_id", NULL_GUID),
        "CSRID": kwargs.get("csr_id", NULL_GUID),
        "InvoiceFreq": kwargs.get("invoice_freq", 3),
        "InvoiceAsWorkOrder": False, "PaymentType": kwargs.get("payment_type", 2),
        "CallAhead": False, "ArrivalWindow": 0,
        "DontApplyMinimumAmount": False, "UseAnnualPricing": False,
        "PONumber": kwargs.get("po_number", ""), "DateSold": sd,
        "WorkOrderNumber": "", "AreaTreatedIDs": [],
        "GroupJobs": False, "GroupName": "",
        "InternalNote": kwargs.get("internal_note", ""), "ShowInternalNoteRow": False,
        "AssignedResourceIDs": kwargs.get("assigned_resources", []),
        "IsComplete": False, "JobType": 5, "Timing": "OneTime",
        "ServiceMode": "", "CommissionType": 0,
        "CommissionOverrideData": {"CommissionIDs": [], "ResourceTypeIDs": [], "AmountList": []},
        "CreateNewProject": False, "IsForProject": False,
        "ProjectID": NULL_GUID, "QuoteID": kwargs.get("quote_id", NULL_GUID),
        "ServiceTypeID": service_type_id, "Assets": [], "PushMultidayAssignments": False,
        "ServiceDetails": [{
            "RouteSheetNotes": [],
            "Products": [], "InstalledProducts": [], "Appointments": [],
            "BudgetedHourOverrides": [],
            "Detail": {
                "ID": NULL_GUID, "ServiceTypeID": service_type_id,
                "ServiceName": service_name, "StartDate": sd, "EndDate": sd,
                "StartTime": kwargs.get("start_time", ""), "EndTime": kwargs.get("end_time", ""),
                "AssignedResourceIDs": kwargs.get("assigned_resources", []),
                "Quantity": kwargs.get("quantity", 1), "Rate": rate, "Hours": hours,
                "BudgetedNumberOfMen": kwargs.get("budgeted_men", 1), "NumberOfDays": 1,
                "InvoiceNotes": kwargs.get("invoice_notes", ""),
                "ServiceMode": "", "Status": 1,
                "DiscountID": NULL_GUID, "DiscountType": 0, "DiscountAmount": 0,
                "DiscountExpiration": {"Month": -1, "Day": -1, "Year": -1},
                "QuoteLineItemID": kwargs.get("quote_line_item_id", NULL_GUID),
                "ProductsRate": 0,
            }
        }],
    }


def _build_recurring_payload(client_guid, service_type_id, service_name, rate,
                             start_date, end_date, schedule_id, schedule_description,
                             days=None, hours=0.5, user_id=USER_ID, job_id=JOB_ID, **kwargs):
    """
    Build a SaveRecurringService payload.
    Uses Service.Details[] (flat), InvoiceFrequency, needs InitialDate.
    """
    sd = _browser_date(start_date)
    ed = _browser_date(end_date)
    if days is None:
        days = {'mon': True, 'tue': True, 'wed': True, 'thu': True, 'fri': True, 'sat': False, 'sun': False}
    return {
        "UserID": user_id, "JobID": job_id, "CustomerID": client_guid,
        "CustomerSourceID": kwargs.get("source_id", NULL_GUID),
        "ContractID": kwargs.get("contract_id", NULL_GUID),
        "ServiceID": NULL_GUID,
        "SalesPersonID": kwargs.get("sales_person_id", NULL_GUID),
        "CSRID": kwargs.get("csr_id", NULL_GUID),
        "InvoiceFrequency": kwargs.get("invoice_frequency", 1),
        "InvoiceAsWorkOrder": False, "PaymentType": kwargs.get("payment_type", 2),
        "CallAhead": False, "ArrivalWindow": 0,
        "DontApplyMinimumAmount": False, "UseAnnualPricing": False,
        "PONumber": kwargs.get("po_number", ""), "DateSold": sd,
        "WorkOrderNumber": "", "AreaTreatedIDs": [],
        "GroupJobs": False, "GroupName": "",
        "IncludeSunday": days.get('sun', False), "IncludeMonday": days.get('mon', False),
        "IncludeTuesday": days.get('tue', False), "IncludeWednesday": days.get('wed', False),
        "IncludeThursday": days.get('thu', False), "IncludeFriday": days.get('fri', False),
        "IncludeSaturday": days.get('sat', False),
        "MaximumManHoursPerDay": kwargs.get("max_hours", "9"),
        "CommissionOverrideData": {"CommissionIDs": [], "ResourceTypeIDs": [], "AmountList": []},
        "CommissionType": 0, "InternalNote": kwargs.get("internal_note", ""),
        "ShowInternalNoteRow": False,
        "AssignedResourceIDs": kwargs.get("assigned_resources", []),
        "IsComplete": False, "JobType": kwargs.get("job_type", 1),
        "Timing": "Recurring", "ScheduleID": schedule_id,
        "ScheduleDescription": schedule_description,
        "ServiceMode": "", "DoNotAutoRenew": kwargs.get("do_not_auto_renew", False),
        "PayUsingBudgetedHours": False, "RecalculateEndDate": False, "AnnualRenewalDate": False,
        "Service": {"Details": [{
            "ID": NULL_GUID, "ServiceTypeID": service_type_id, "ServiceName": service_name,
            "StartDate": sd, "EndDate": ed,
            "StartTime": kwargs.get("start_time", ""), "EndTime": kwargs.get("end_time", ""),
            "AssignedResourceIDs": kwargs.get("assigned_resources", []),
            "Quantity": kwargs.get("quantity", 1), "Rate": rate, "Hours": hours,
            "BudgetedNumberOfMen": kwargs.get("budgeted_men", 1), "NumberOfDays": 1,
            "InvoiceNotes": kwargs.get("invoice_notes", ""),
            "RouteSheetNotes": [],
            "Products": [], "InstalledProducts": [],
            "InitialDate": sd,  # Required for recurring
            "Appointments": [], "BudgetedHourOverrides": [],
            "ServiceMode": "", "Status": 1,
            "DiscountID": NULL_GUID, "DiscountType": 0, "DiscountAmount": 0,
            "DiscountExpiration": {"Month": -1, "Day": -1, "Year": -1},
            "QuoteLineItemID": kwargs.get("quote_line_item_id", NULL_GUID), "ProductsRate": 0,
        }]},
        "CreateNewProject": False, "IsForProject": False,
        "ProjectID": NULL_GUID, "QuoteID": kwargs.get("quote_id", NULL_GUID),
        "ServiceTypeID": service_type_id, "Assets": [], "PushMultidayAssignments": False,
    }


def _build_on_demand_payload(client_guid, service_type_id, service_name, rate,
                             budgeted_hours=1, invoice_type=1, **kwargs):
    """
    Build a SnowEditorWs.asmx/Save payload.
    Completely different structure: sub-models, InputData wrapper, null DiscountExpiration.
    """
    return {
        "errors": [],
        "ScheduledServiceID": kwargs.get("service_id", NULL_GUID),
        "ScheduledServicePriceID": NULL_GUID,
        "QuoteLineItemID": kwargs.get("quote_line_item_id", NULL_GUID),
        "JobInfoModel": {
            "CustomerID": client_guid,
            "ServiceTypeID": service_type_id,
            "ServiceTypeName": service_name,
            "AssignedResources": kwargs.get("assigned_resources", []),
            "InchTrigger": kwargs.get("inch_trigger", 0),
            "DaysAuthorized": kwargs.get("days_authorized", [False]*7),
        },
        "InvoiceSetupModel": {
            "InvoiceTypeEnum": invoice_type,
            "ContractID": kwargs.get("contract_id", NULL_GUID),
            "CapTypeEnum": kwargs.get("cap_type", 0),
            "Cap": kwargs.get("cap", 0),
            "CapResetTypeEnum": kwargs.get("cap_reset_type", 0),
            "Overage": kwargs.get("overage", ""),
        },
        "RateMatrixModel": {
            "GroupRanges": [{
                "AssetTypeID": NULL_GUID,
                "Matrices": [{
                    "ScheduledServiceMatrixID": NULL_GUID,
                    "From": kwargs.get("from_depth", 0), "To": kwargs.get("to_depth", 0),
                    "RateTypeEnum": kwargs.get("rate_type_enum", 0),
                    "Rate": rate, "BudgetedHours": budgeted_hours,
                    "InvoiceDescription": kwargs.get("invoice_description", ""),
                }],
            }],
            "DeletedMatrices": [],
        },
        "DetailsModel": {
            "CallAhead": kwargs.get("call_ahead", False),
            "PONumber": kwargs.get("po_number", ""),
            "DiscountID": NULL_GUID,
            "DiscountExpiration": None,  # MUST be null
            "DiscountAmount": str(kwargs.get("discount_amount", "0")),
            "SalesRepID": kwargs.get("sales_rep_id", NULL_GUID),
            "SourceID": kwargs.get("source_id", NULL_GUID),
            "CSRID": kwargs.get("csr_id", NULL_GUID),
            "MethodOfPaymentEnum": kwargs.get("payment_method", 2),
            "PayUsingBHrs": kwargs.get("pay_using_bhrs", False),
            "CompensationTypeEnum": kwargs.get("commission_type", 0),
        },
        "NotesModel": {"JobNotes": [], "DeletedJobNotes": [], "InvoiceDescription": kwargs.get("invoice_notes", "")},
        "ProductsModel": {"Products": [], "DeletedProducts": []},
    }


def _build_waiting_list_payload(client_guid, service_type_id, service_name, rate,
                            start_date, complete_by_date, hours=0.5, user_id=USER_ID, job_id=JOB_ID, **kwargs):
    """
    Build a SaveWaitingListService payload.
    Same structure as OneTime (ServiceDetails[{Detail:{}}]) but with:
    - EndDate = 'Complete By' date (required, must be valid)
    - CustomPackageID, IsRenewable, RenewStartDate, RenewEndDate fields
    - No JobType or Timing field (endpoint handles that)
    """
    sd = _browser_date(start_date)
    ed = _browser_date(complete_by_date)
    return {
        'UserID': user_id, 'JobID': job_id, 'CustomerID': client_guid,
        'CustomerSourceID': kwargs.get('source_id', NULL_GUID),
        'ContractID': kwargs.get('contract_id', NULL_GUID),
        'ServiceID': NULL_GUID,
        'SalesPersonID': kwargs.get('sales_person_id', NULL_GUID),
        'CSRID': kwargs.get('csr_id', NULL_GUID),
        'InvoiceFreq': kwargs.get('invoice_freq', 3),
        'InvoiceAsWorkOrder': False, 'PaymentType': kwargs.get('payment_type', 2),
        'CallAhead': False, 'ArrivalWindow': 0,
        'DontApplyMinimumAmount': False, 'UseAnnualPricing': False,
        'PONumber': kwargs.get('po_number', ''), 'DateSold': sd,
        'WorkOrderNumber': '', 'AreaTreatedIDs': [],
        'GroupJobs': False, 'GroupName': '',
        'AssignedResourceIDs': kwargs.get('assigned_resources', []),
        'InternalNote': kwargs.get('internal_note', ''), 'ShowInternalNoteRow': False,
        'CommissionType': 0,
        'CommissionOverrideData': {'CommissionIDs': [], 'ResourceTypeIDs': [], 'AmountList': []},
        'QuoteID': kwargs.get('quote_id', NULL_GUID), 'Assets': [],
        'ServiceTypeID': service_type_id,
        'CustomPackageID': kwargs.get('custom_package_id', NULL_GUID),
        'IsRenewable': kwargs.get('is_renewable', False),
        'RenewStartDate': kwargs.get('renew_start_date', None),
        'RenewEndDate': kwargs.get('renew_end_date', None),
        'PushMultidayAssignments': False,
        'ServiceDetails': [{
            'Detail': {
                'ID': NULL_GUID,
                'AssignedResourceIDs': kwargs.get('assigned_resources', []),
                'OriginalAssignedResourceIDs': [],
                'ServiceTypeID': service_type_id, 'ServiceName': service_name,
                'Quantity': kwargs.get('quantity', 1), 'Rate': rate, 'Hours': hours,
                'InvoiceNotes': kwargs.get('invoice_notes', ''),
                'StartDate': sd, 'EndDate': ed,
                'Status': 1, 'StartTime': '', 'EndTime': '',
                'ProjectDay': 0, 'BillableHours': '0.00', 'NumberOfMen': 0,
                'DiscountID': NULL_GUID, 'DiscountType': 0, 'DiscountAmount': 0,
                'DiscountExpiration': {'Month': -1, 'Day': -1, 'Year': -1},
                'Include': False, 'BudgetedNumberOfMen': kwargs.get('budgeted_men', 1),
                'NumberOfDays': 1,
                'QuoteLineItemID': kwargs.get('quote_line_item_id', NULL_GUID),
                'ProductsRate': 0,
            },
            'Products': [], 'InstalledProducts': [], 'RouteSheetNotes': [],
            'BudgetedHourOverrides': [], 'Appointments': [],
        }],
    }

def _build_package_payload(client_guid, selected_package_id, services,
                             user_id=USER_ID, job_id=JOB_ID, **kwargs):
    """
    Build a SavePackage payload.
    Structure: {"Input": {SelectedPackageID, Services[], RouteSheetNotes[], ...}}
    Completely different from OneTime/Recurring/WaitingList.
    """
    return {
        "UserID": user_id, "JobID": job_id, "CustomerID": client_guid,
        "CustomerSourceID": kwargs.get("source_id", NULL_GUID),
        "ContractID": kwargs.get("contract_id", NULL_GUID),
        "ServiceID": kwargs.get("service_id", NULL_GUID),
        "SalesPersonID": kwargs.get("sales_person_id", NULL_GUID),
        "CSRID": kwargs.get("csr_id", NULL_GUID),
        "InvoiceFreq": kwargs.get("invoice_freq", 1),
        "InvoiceAsWorkOrder": False, "PaymentType": kwargs.get("payment_type", 2),
        "CallAhead": False, "ArrivalWindow": 0,
        "DontApplyMinimumAmount": False, "UseAnnualPricing": False,
        "PONumber": kwargs.get("po_number", ""),
        "DateSold": _browser_date(kwargs.get("date_sold", {"Year": 2026, "Month": 1, "Day": 1})),
        "WorkOrderNumber": kwargs.get("work_order_number", ""),
        "AreaTreatedIDs": [],
        "GroupJobs": False, "GroupName": "",
        "IncludeSunday": False, "IncludeMonday": True, "IncludeTuesday": True,
        "IncludeWednesday": True, "IncludeThursday": True, "IncludeFriday": True,
        "IncludeSaturday": False,
        "MaximumManHoursPerDay": kwargs.get("max_hours", "9"),
        "CommissionOverrideData": {"CommissionIDs": [], "ResourceTypeIDs": [], "AmountList": []},
        "CommissionType": 0,
        "InternalNote": kwargs.get("internal_note", ""),
        "ShowInternalNoteRow": False,
        "PackageID": kwargs.get("package_id", NULL_GUID),
        "SelectedPackageID": selected_package_id,
        "RenewalOption": kwargs.get("renewal_option", 2),
        "AssignedResourceIDs": kwargs.get("assigned_resources", []),
        "RenewPackage": kwargs.get("renew_package", False),
        "ExcludeSunday": False, "ExcludeMonday": False, "ExcludeTuesday": False,
        "ExcludeWednesday": False, "ExcludeThursday": False, "ExcludeFriday": False,
        "ExcludeSaturday": False,
        "Services": services,
        "RouteSheetNotes": kwargs.get("route_sheet_notes", []),
        "ServiceItems": {"Assets": []},
    }


def build_package_service(description, rate=0, quantity=1, hours=1.5, service_id=NULL_GUID,
                          budgeted_men=1, num_days=1, add_to_schedule=False, is_active=True,
                          quote_line_item_id=NULL_GUID):
    """Build a single service entry for a package job's Services[] array."""
    return {
        "ID": service_id, "Description": description, "Rate": rate,
        "Quantity": quantity, "Hours": hours,
        "BudgetedNumberOfMen": budgeted_men, "NumberOfDays": num_days,
        "AddToSchedule": add_to_schedule, "IsActive": is_active,
        "Products": [], "InstalledProducts": [],
        "DiscountID": NULL_GUID, "DiscountType": 0, "DiscountAmount": 0,
        "DiscountExpiration": {"Month": -1, "Day": -1, "Year": -1},
        "QuoteLineItemID": quote_line_item_id,
    }


def build_common_fields(client_guid, service_id=NULL_GUID, **kwargs):
    """Build common field structure (legacy compat)."""
    data = {
        "UserID": USER_ID, "JobID": JOB_ID, "CustomerID": client_guid,
        "ServiceID": service_id,
        "CustomerSourceID": kwargs.get("source_id", NULL_GUID),
        "ContractID": kwargs.get("contract_id", NULL_GUID),
        "SalesPersonID": kwargs.get("sales_person_id", NULL_GUID),
        "CSRID": kwargs.get("csr_id", NULL_GUID),
        "InvoiceFreq": kwargs.get("invoice_freq", 3),
        "InvoiceAsWorkOrder": False, "PaymentType": kwargs.get("payment_type", 1),
        "CallAhead": False, "ArrivalWindow": 0,
        "DontApplyMinimumAmount": False, "UseAnnualPricing": False,
        "PONumber": "", "WorkOrderNumber": "", "AreaTreatedIDs": [],
        "GroupJobs": False, "GroupName": "",
        "InternalNote": kwargs.get("internal_note", ""), "ShowInternalNoteRow": False,
        "CommissionType": 0,
    }
    if kwargs.get("date_sold"):
        data["DateSold"] = _browser_date(kwargs["date_sold"])
    return data
