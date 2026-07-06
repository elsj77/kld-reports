"""
sap_installment_plans.py — Installment Plan / Contract Operations
Endpoints: ContractsWs.asmx (16 confirmed ops), AccountingBFF/ContractList

NOTE: CRMBFF/InstallmentPlan/* endpoints return 404 — InstallmentPlan data
is served via ContractsWs.asmx and AccountingBFF/ContractList (confirmed 2026-06-26).

ContractsWs operations:
  GetContractStatusList, Query, ExportContracts, GenerateInvoices,
  UpdateContractStatus, GetContract, SaveContract, GetScheduledServices,
  ToggleContractActive, GetContractLineItems, ToggleAutoGenerate,
  CalculateSalesTax, BulkPriceInstallmentPlansUpdate, GetCustomerData,
  GetNotes, CreateNewInvoices

Legacy V2 → V3 migration: ConvertToV3InstallmentPlan (ContractsWS.asmx)
"""
from .sap_core import SAPClient, get_sap, NULL_GUID


class InstallmentPlansAPI:
    def __init__(self, sap=None):
        self.sap = sap or get_sap()

    # ─── LIST / QUERY ─────────────────────────────────────────────────────────

    def query(self, start_row=1, max_rows=22, filters=None):
        """Query the installment plan / contract list.
        Returns paginated list of contracts.
        """
        return self.sap.post("/AccountingBFF/ContractList/Query", {
            "QueryInput": {
                "StartRow": start_row,
                "Max": max_rows,
                "ScreenViewFilterTypes": filters or [],
                "SortedColumns": []
            }
        })

    def query_by_ids(self, contract_ids):
        """Get contracts by list of GUIDs."""
        return self.sap.post("/AccountingBFF/ContractList/QueryByIDs", {
            "IDs": contract_ids
        })

    def query_totals(self, filters=None):
        """Get total contract count + IDs."""
        return self.sap.post("/AccountingBFF/ContractList/QueryTotals", {
            "QueryInput": {
                "StartRow": 1,
                "Max": 1,
                "ScreenViewFilterTypes": filters or [],
                "SortedColumns": []
            }
        })

    # ─── GET SINGLE CONTRACT ──────────────────────────────────────────────────

    def get(self, contract_id):
        """Get full contract/installment plan data.
        contract_id: contract GUID
        """
        return self.sap.post("/webservices/ContractsWs.asmx/GetContract", {
            "ContractID": contract_id
        })

    def get_customer_data(self, contract_id):
        """Get the client data associated with a contract."""
        return self.sap.post("/webservices/ContractsWs.asmx/GetCustomerData", {
            "ContractID": contract_id
        })

    def get_notes(self, contract_id):
        """Get notes on a contract."""
        return self.sap.post("/webservices/ContractsWs.asmx/GetNotes", {
            "ContractID": contract_id
        })

    def get_line_items(self, contract_id):
        """Get line items for a contract."""
        return self.sap.post("/webservices/ContractsWs.asmx/GetContractLineItems", {
            "ContractID": contract_id
        })

    def get_scheduled_services(self, contract_id):
        """Get scheduled services associated with a contract."""
        return self.sap.post("/webservices/ContractsWs.asmx/GetScheduledServices", {
            "ContractID": contract_id
        })

    # ─── STATUS MANAGEMENT ────────────────────────────────────────────────────

    def get_status_list(self):
        """Get all available contract status options."""
        return self.sap.post("/webservices/ContractsWs.asmx/GetContractStatusList", {})

    def update_status(self, contract_ids, status):
        """Update status on one or more contracts.
        contract_ids: list of contract GUIDs
        status: status value from get_status_list()
        """
        return self.sap.post("/webservices/ContractsWs.asmx/UpdateContractStatus", {
            "ContractIDs": contract_ids,
            "Status": status
        })

    def toggle_active(self, contract_id, active=True):
        """Activate or deactivate a contract."""
        return self.sap.post("/webservices/ContractsWs.asmx/ToggleContractActive", {
            "ContractID": contract_id,
            "Active": active
        })

    def toggle_auto_generate(self, contract_id, enabled=True):
        """Toggle auto-generate invoices on a contract."""
        return self.sap.post("/webservices/ContractsWs.asmx/ToggleAutoGenerate", {
            "ContractID": contract_id,
            "Enabled": enabled
        })

    # ─── SAVE / CREATE ────────────────────────────────────────────────────────

    def save(self, contract_data):
        """Create or update a contract/installment plan.
        contract_data: full contract payload object.
        Use get() on an existing contract to understand the shape before saving.
        """
        return self.sap.post("/webservices/ContractsWs.asmx/SaveContract", {
            "ContractData": contract_data
        })

    # ─── INVOICES FROM CONTRACT ───────────────────────────────────────────────

    def generate_invoices(self, contract_ids):
        """Generate invoices from contracts (manual trigger).
        contract_ids: list of contract GUIDs
        """
        return self.sap.post("/webservices/ContractsWs.asmx/GenerateInvoices", {
            "ContractIDs": contract_ids
        })

    def create_new_invoices(self, contract_id):
        """Create new invoices for a contract."""
        return self.sap.post("/webservices/ContractsWs.asmx/CreateNewInvoices", {
            "ContractID": contract_id
        })

    # ─── BULK OPERATIONS ─────────────────────────────────────────────────────

    def bulk_price_update(self, contract_ids, price_data):
        """Bulk price update across installment plans.
        contract_ids: list of contract GUIDs
        price_data: price update payload
        """
        return self.sap.post("/webservices/ContractsWs.asmx/BulkPriceInstallmentPlansUpdate", {
            "ContractIDs": contract_ids,
            "PriceData": price_data
        })

    def export(self, contract_ids):
        """Export contracts to CSV/report."""
        return self.sap.post("/webservices/ContractsWs.asmx/ExportContracts", {
            "ContractIDs": contract_ids
        })

    # ─── SALES TAX ────────────────────────────────────────────────────────────

    def calculate_sales_tax(self, contract_id):
        """Calculate sales tax for a contract."""
        return self.sap.post("/webservices/ContractsWs.asmx/CalculateSalesTax", {
            "ContractID": contract_id
        })

    # ─── V2 → V3 MIGRATION ───────────────────────────────────────────────────

    def convert_to_v3(self, contract_ids):
        """Convert legacy V2 contracts to V3 installment plans.
        contract_ids: list of legacy contract GUIDs
        """
        return self.sap.post("/webservices/ContractsWS.asmx/ConvertToV3InstallmentPlan", {
            "ContractIDs": contract_ids
        })
