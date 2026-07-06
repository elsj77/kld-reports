"""
sap_contracts.py — Contract / Installment Plan Operations
Endpoints: ContractsWs (19 ops confirmed), AccountingBFF/ContractList,
           ClientViewWs (per-client contract helpers)

TWO CONTRACT LAYERS:
  Legacy: /webservices/ContractsWS.asmx  — query list, bulk ops, V2→V3 migration
  v3:     /v3/WebServices/Accounting/ContractsWs.asmx — get/save/CRUD on single contracts

ContractModel fields (full payload for SaveContract):
  ContractID, CustomerJobID, ClientID, StartDate, EndDate,
  JanuaryAmount–DecemberAmount (per-month breakdown),
  Active, BillInAdvance, AutoGenerate, BillingDayOfMonth,
  ContractName, Description, ServiceTypeID, PONumber,
  CsrUserID, SalesRepID, CustomerSourceID,
  MethodOfPayment (0=default), ContractServiceList[], ContractLineItems[]

KLD has 41 contracts total.
"""
from .sap_core import SAPClient, get_sap, NULL_GUID


class ContractsAPI:
    def __init__(self, sap=None):
        self.sap = sap or get_sap()

    # ─── LIST / QUERY ─────────────────────────────────────────────────────────

    def query(self, start_row=1, max=22, filters=None):
        """Query contract list (AccountingBFF — v3 SPA backing).
        Returns: {ContractItems: [{ClientID, ContractID, ClientName, Service,
                  BillingDay, Amount, StartDate, EndDate, Active, ...}],
                  ContractsTotal}
        """
        return self.sap.post("/AccountingBFF/ContractList/Query", {
            "QueryInput": {
                "StartRow": start_row,
                "Max": max,
                "ActiveTab": "",
                "ScreenViewFilterTypes": filters or [],
                "SortedColumns": []
            }
        })

    def query_legacy(self, client="", service="", billing_day=0,
                     start_row=1, max_rows=50, filter_tab=0, tag_ids=None):
        """Query contract list via legacy ContractsWS endpoint.
        Supports richer filtering: client name, service, billing day, tags.
        Returns: {ContractItems, ContractsTotal, BatchExportEnabled}
        """
        return self.sap.post("/webservices/ContractsWS.asmx/Query", {
            "Input": {
                "FilterData": {
                    "Client": client,
                    "Service": service,
                    "BillingDay": billing_day,
                    "Amount": "",
                    "StartDateFrom": "",
                    "StartDateTo": "",
                    "EndDateFrom": "",
                    "EndDateTo": "",
                    "TagIDs": tag_ids or [],
                    "DoesNotHaveTagIDs": []
                },
                "StartRow": start_row,
                "MaxRows": max_rows,
                "FilterTab": filter_tab
            }
        })

    def query_by_ids(self, contract_ids):
        """Get specific contracts by GUID list."""
        return self.sap.post("/AccountingBFF/ContractList/QueryByIDs", {
            "IDs": contract_ids
        })

    def query_totals(self, filters=None):
        """Get contract list totals and IDs."""
        return self.sap.post("/AccountingBFF/ContractList/QueryTotals", {
            "QueryInput": {
                "StartRow": 1, "Max": 1,
                "ActiveTab": "",
                "ScreenViewFilterTypes": filters or [],
                "SortedColumns": []
            }
        })

    # ─── GET SINGLE CONTRACT ──────────────────────────────────────────────────

    def get(self, contract_id):
        """Get full contract record (30 fields including monthly amounts).
        Returns: ContractData with JanuaryAmount–DecemberAmount,
                 Active, BillInAdvance, AutoGenerate, ContractServiceList, etc.
        """
        return self.sap.post("/v3/WebServices/Accounting/ContractsWs.asmx/GetContract", {
            "ContractID": contract_id
        })

    def get_for_client(self, customer_job_id):
        """Get contracts for a specific client (recent, via ClientViewWs).
        customer_job_id: CustomerJobID from client.get()
        Returns: {Contracts, ContractTotal}
        """
        return self.sap.post("/WebServices/ClientViewWs.asmx/GetRecentContractsAsync", {
            "request": {"CustomerJobID": customer_job_id}
        })

    def get_expanded_for_client(self, customer_job_id):
        """Get expanded contract list for a client (full detail).
        customer_job_id: CustomerJobID from client.get()
        """
        return self.sap.post("/WebServices/ClientViewWs.asmx/GetExpandedContracts", {
            "request": {
                "CustomerJobID": customer_job_id,
                "AllJobs": True,
                "Start": 0,
                "Total": 25,
                "ShowMore": False
            }
        })

    def get_customer_data(self, customer_job_id):
        """Get client data associated with a contract (for overlay population).
        NOTE: Uses CustomerJobID (not ClientID/ContractID).
        """
        return self.sap.post("/v3/WebServices/Accounting/ContractsWs.asmx/GetCustomerData", {
            "CustomerJobID": customer_job_id
        })

    def get_notes(self, contract_id):
        """Get notes on a contract.
        Returns: ContractNoteData[] with ContractNoteID, Note, DateCreated, DateModified
        """
        return self.sap.post("/v3/WebServices/Accounting/ContractsWs.asmx/GetNotes", {
            "ContractID": contract_id
        })

    def get_line_items(self, contract_id):
        """Get line items for a contract."""
        return self.sap.post("/v3/WebServices/Accounting/ContractsWs.asmx/GetContractLineItems", {
            "ContractID": contract_id
        })

    def get_scheduled_services(self, contract_id):
        """Get scheduled services associated with a contract."""
        return self.sap.post("/v3/WebServices/Accounting/ContractsWs.asmx/GetScheduledServices", {
            "ContractID": contract_id
        })

    def check_getting_started(self):
        """Check if the getting-started overlay should be shown for contracts."""
        return self.sap.post("/webservices/ContractsWS.asmx/CheckGettingStarted", {})

    # ─── CREATE / UPDATE ──────────────────────────────────────────────────────

    def get_template(self):
        """Return a blank ContractModel payload with safe defaults.
        Populate CustomerJobID, ContractName, ServiceTypeID, monthly amounts, dates.
        Pass NULL_GUID as ContractID to create new.
        """
        return {
            "ContractID": NULL_GUID,
            "CustomerJobID": NULL_GUID,
            "ClientID": NULL_GUID,
            "StartDate": "",
            "EndDate": "",
            "JanuaryAmount": 0.00,
            "FebruaryAmount": 0.00,
            "MarchAmount": 0.00,
            "AprilAmount": 0.00,
            "MayAmount": 0.00,
            "JuneAmount": 0.00,
            "JulyAmount": 0.00,
            "AugustAmount": 0.00,
            "SeptemberAmount": 0.00,
            "OctoberAmount": 0.00,
            "NovemberAmount": 0.00,
            "DecemberAmount": 0.00,
            "Active": True,
            "BillInAdvance": False,
            "AutoGenerate": True,
            "BillingDayOfMonth": 1,
            "ContractName": "",
            "Description": "",
            "ServiceTypeID": NULL_GUID,
            "PONumber": "",
            "CsrUserID": NULL_GUID,
            "SalesRepID": NULL_GUID,
            "CustomerSourceID": NULL_GUID,
            "MethodOfPayment": 0,
            "HasCreditCardOnFile": False,
            "CanUploadAttachments": False,
            "IncludeSubProperties": True,
            "ContractServiceList": [],
            "ContractLineItems": []
        }

    def save(self, contract_data):
        """Create or update a contract.
        Use get_template() to get the base payload, then populate fields.
        NULL_GUID as ContractID = create new.
        Returns: {ContractID, Errors}
        """
        return self.sap.post("/v3/WebServices/Accounting/ContractsWs.asmx/SaveContract",
                              contract_data)

    # ─── STATUS / LIFECYCLE ───────────────────────────────────────────────────

    def get_status_list(self):
        """Get contract status options: open, paid, past due."""
        return self.sap.post("/v3/WebServices/Accounting/ContractsWs.asmx/GetContractStatusList", {})

    def update_status(self, contract_ids, active=True):
        """Activate or deactivate contracts.
        contract_ids: list of contract GUIDs
        active: True=activate, False=deactivate
        """
        return self.sap.post("/webservices/ContractsWS.asmx/UpdateContractStatus", {
            "Input": {"ContractIDs": contract_ids, "Active": active}
        })

    def toggle_active(self, contract_id):
        """Toggle active/inactive on a single contract (v3)."""
        return self.sap.post("/v3/WebServices/Accounting/ContractsWs.asmx/ToggleContractActive", {
            "ContractID": contract_id
        })

    def toggle_auto_generate(self, contract_id):
        """Toggle auto-generate invoices on a contract."""
        return self.sap.post("/v3/WebServices/Accounting/ContractsWs.asmx/ToggleAutoGenerate", {
            "ContractID": contract_id
        })

    # ─── INVOICES FROM CONTRACT ───────────────────────────────────────────────

    def generate_invoices(self, contract_id):
        """Generate invoices for a contract (v3)."""
        return self.sap.post("/v3/WebServices/Accounting/ContractsWs.asmx/GenerateInvoices", {
            "ContractID": contract_id
        })

    def create_invoices(self, contract_ids, invoice_date=None):
        """Create invoices for contracts on a specific date (legacy batch).
        invoice_date: dict {Month, Day, Year} — defaults to today
        """
        import datetime
        today = datetime.date.today()
        date = invoice_date or {"Month": today.month, "Day": today.day, "Year": today.year}
        return self.sap.post("/webservices/ContractsWS.asmx/CreateInvoices", {
            "Input": {"ContractIDs": contract_ids, "InvoiceDate": date}
        })

    def create_new_invoices(self, contract_id):
        """Create new invoices for a single contract (v3)."""
        return self.sap.post("/v3/WebServices/Accounting/ContractsWs.asmx/CreateNewInvoices", {
            "ContractID": contract_id
        })

    # ─── BULK / EXPORT ────────────────────────────────────────────────────────

    def bulk_price_update(self, contract_ids, price_data):
        """Bulk price update across multiple contracts."""
        return self.sap.post("/v3/WebServices/Accounting/ContractsWs.asmx/BulkPriceInstallmentPlansUpdate", {
            "ContractIDs": contract_ids,
            "PriceData": price_data
        })

    def export(self, filter_data=None, start_row=1, max_rows=500):
        """Export contracts to file (legacy endpoint)."""
        return self.sap.post("/webservices/ContractsWS.asmx/ExportContracts", {
            "Input": {
                "FilterData": filter_data or {
                    "Client": "", "Service": "", "BillingDay": 0, "Amount": "",
                    "StartDateFrom": "", "StartDateTo": "", "EndDateFrom": "",
                    "EndDateTo": "", "TagIDs": [], "DoesNotHaveTagIDs": []
                },
                "StartRow": start_row,
                "MaxRows": max_rows,
                "FilterTab": 0
            }
        })

    def calculate_sales_tax(self, tax_data):
        """Calculate sales tax for a contract."""
        return self.sap.post("/v3/WebServices/Accounting/ContractsWs.asmx/CalculateSalesTax", tax_data)

    # ─── V2 → V3 MIGRATION ───────────────────────────────────────────────────

    def convert_to_v3(self, contract_ids):
        """Convert legacy V2 contracts to V3 installment plans."""
        return self.sap.post("/webservices/ContractsWS.asmx/ConvertToV3InstallmentPlan", {
            "ContractIDs": contract_ids
        })

    # ─── HELPERS ─────────────────────────────────────────────────────────────

    def get_all_active(self):
        """Get all active contracts (legacy query, no date filter)."""
        return self.query_legacy(filter_tab=0)

    def set_monthly_amount(self, contract_id, monthly_amount):
        """Set the same amount for every month on a contract.
        Fetches current data, sets all 12 month amounts, saves.
        """
        current = self.get(contract_id)
        if isinstance(current, dict) and "d" in current:
            current = current["d"]
        months = ["January", "February", "March", "April", "May", "June",
                  "July", "August", "September", "October", "November", "December"]
        for m in months:
            current[f"{m}Amount"] = monthly_amount
        return self.save(current)
