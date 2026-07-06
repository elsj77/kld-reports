"""
sap_clients.py — Client/Lead CRM Operations
Endpoints: ClientViewWs, ClientEditOverlayWs, ClientsWs, CRMBFF/AccountList,
           CRMBFF/CustomerSearch, CRMBFF/ClientView, ClientUpdateWs, TagsWs,
           SchedulingBFF/CalendarEvent, MapsWs

KEY GUIDs (KLD — BC/Canada):
  StateID (BC):        235cc50f-dc1c-4571-80ec-04050eb615e8
  CountryID (Canada):  9d09a286-14ac-4661-ad8f-d8984ef3e6b6
  ListID (active):     800015E8-1634312010
  PaymentMethodID:     9f4fa52f-8323-4ee2-b8a5-194d58266d44
  SalesTaxCodeID:      4cbedc03-5981-458f-80c0-23487d8db8ba
  StandardTermID:      0c7dc766-64e8-4496-92af-b1d5f38fb9ae

SANDBOX TEST CLIENT:
  GUID:          11799600-51d4-40f8-8ff8-73b5c7581d2a
  CustomerJobID: a32175e7-df9c-4baf-a3dd-e2379826db02

BILLING PROTECTION:
  NEVER include CC/payment fields in SaveClient payloads.
  Fields: CCFirstName, CCLastName, CCNumber, CCToken, CCCustomerToken, etc.
"""
from .sap_core import SAPClient, get_sap, NULL_GUID, COMPANY_ID

# KLD-specific GUIDs (BC/Canada defaults)
BC_STATE_ID      = "235cc50f-dc1c-4571-80ec-04050eb615e8"
CANADA_COUNTRY   = "9d09a286-14ac-4661-ad8f-d8984ef3e6b6"
ACTIVE_LIST_ID   = "800015E8-1634312010"
DEFAULT_PAYMENT  = "9f4fa52f-8323-4ee2-b8a5-194d58266d44"
SALES_TAX_CODE   = "4cbedc03-5981-458f-80c0-23487d8db8ba"
STANDARD_TERM    = "0c7dc766-64e8-4496-92af-b1d5f38fb9ae"


class ClientsAPI:
    def __init__(self, sap=None):
        self.sap = sap or get_sap()

    # ─── SEARCH / LIST ────────────────────────────────────────────────────────

    def search(self, term, max_results=50):
        """Fast global client+lead search.
        Returns: [{CustomerID, FirstName, LastName, Address, Phone, ...}]
        """
        return self.sap.post("/CRMBFF/CustomerSearch/SearchClientsLeads", {
            "SearchString": term
        })

    def query_list(self, start_row=1, max=22, filters=None):
        """Query the full account list with optional filters.
        filters: list of ScreenViewFilterType dicts
        """
        return self.sap.post("/CRMBFF/AccountList/V2AccountList_Query", {
            "QueryInput": {
                "StartRow": start_row,
                "Max": max,
                "ScreenViewFilterTypes": filters or [],
                "SortedColumns": []
            }
        })

    def query_totals(self, filters=None):
        """Get total account count."""
        return self.sap.post("/CRMBFF/AccountList/V2AccountList_QueryTotals", {
            "QueryInput": {
                "StartRow": 1,
                "Max": 1,
                "ScreenViewFilterTypes": filters or [],
                "SortedColumns": []
            }
        })

    # ─── GET CLIENT DATA ─────────────────────────────────────────────────────

    def get(self, client_guid):
        """Full client record including CustomerJobID, contact info, billing.
        Returns: {CustomerID, CustomerJobID, FirstName, LastName, Email, Phone, ...}
        CustomerJobID is required by many other endpoints.
        """
        return self.sap.post("/WebServices/ClientViewWs.asmx/GetCustomerDataAsync", {
            "customerId": client_guid
        })

    def get_edit_info(self, client_guid):
        """Get client record in edit format (for pre-filling SaveClient).
        Returns same fields as SaveClient payload.
        Use this before calling save() to get current values.
        """
        return self.sap.post("/webservices/ClientEditOverlayWs.asmx/GetClientInfo", {
            "ClientID": client_guid
        })

    def get_contacts(self, client_guid):
        """All contacts on a client."""
        return self.sap.post("/CRMBFF/ClientView/ClientView_GetContacts", {
            "CustomerID": client_guid
        })

    def get_properties(self, client_guid):
        """Properties (service locations) for a client.
        Returns: [{ID, Name, Address, ...}]
        Use property ID for GetPropertyMeasurementCount.
        """
        return self.sap.post("/CRMBFF/ClientView/ClientView_GetPropertiesForPropertySection", {
            "CustomerID": client_guid
        })

    def get_property_measurement_count(self, customer_job_id, property_id):
        """Get property measurement count for a specific property.
        customer_job_id: from get() → CustomerJobID
        property_id: from get_properties() → Properties[].ID
        Returns: {Count: N}
        """
        return self.sap.post("/CRMBFF/ClientView/ClientView_GetPropertyMeasurementCount", {
            "customerJobId": customer_job_id,
            "propertyId": property_id
        })

    def get_account_address(self, customer_job_id):
        """Get account address for calendar/scheduling event.
        customer_job_id: CustomerJobID (NOT CustomerID — common mistake)
        Returns: {Address, City, State, PostalCode, Lat, Lng, ...}
        """
        return self.sap.post("/SchedulingBFF/CalendarEvent/GetAccountAddress", {
            "customerJobId": customer_job_id
        })

    def get_accounting(self, client_guid, max_to_load=100):
        """Full transaction history (invoices + payments) for a client."""
        return self.sap.post("/WebServices/ClientViewWs.asmx/GetAccountingList", {
            "Data": {"CustomerID": client_guid, "AllJobs": True, "MaxToLoad": max_to_load}
        })

    def get_all_services(self, client_guid):
        """All services (jobs + packages) on a client."""
        return self.sap.post_with_referer(
            "/WebServices/ClientViewWs.asmx/GetAllServicesAsync",
            {"request": {"CustomerId": client_guid}},
            "/ClientView.aspx"
        )

    def get_upcoming_services(self, client_guid):
        """Upcoming scheduled services for a client."""
        return self.sap.post_with_referer(
            "/WebServices/ClientViewWs.asmx/GetUpcomingServicesAsync",
            {"request": {"CustomerId": client_guid}},
            "/ClientView.aspx"
        )

    def get_service_history(self, client_guid):
        """Service history log for a client."""
        return self.sap.post("/CRMBFF/ClientView/ClientView_GetServiceHistory", {
            "CustomerID": client_guid
        })

    def get_estimates(self, customer_job_id):
        """All estimates for a client.
        Requires CustomerJobID (from get()), NOT CustomerID.
        """
        return self.sap.post("/CRMBFF/Quote/GetV2Estimates", {
            "request": {"CustomerJobID": customer_job_id, "IsLead": False, "OnlyRecent": False}
        })

    def get_activity_stream(self, client_guid):
        """Full activity timeline for a client (notes, calls, emails, jobs)."""
        return self.sap.post("/CRMBFF/AccountReview/GetClientActivityStream", {
            "ID": client_guid
        })

    def get_installed_products(self, client_guid):
        """Installed products / assets on a client."""
        return self.sap.post("/WebServices/ClientViewWs.asmx/GetInstalledProducts", {
            "customerId": client_guid
        })

    def get_damage_cases(self, client_guid):
        """Damage case records for a client."""
        return self.sap.post("/WebServices/ClientViewWs.asmx/GetDamageCases", {
            "customerId": client_guid
        })

    # ─── CUSTOM FIELDS ────────────────────────────────────────────────────────

    def get_custom_fields(self, client_guid):
        """Get custom field values for a client (display format).
        Returns: [{CustomFieldID, CustomFieldName, CustomFieldValue, ...}]
        Use KLD field GUIDs from sap_static_ids rule for targeting specific fields.
        """
        return self.sap.post("/WebServices/ClientViewWs.asmx/GetCustomFields", {
            "customerId": client_guid
        })

    def get_custom_fields_for_edit(self, client_guid):
        """Get custom fields in edit format (from overlay — richer schema).
        Returns: [{CustomFieldID, CustomFieldName, CustomFieldValue, CustomFieldValueType, listItems, ...}]
        """
        return self.sap.post("/webservices/ClientEditOverlayWs.asmx/GetCustomFieldList", {
            "ClientID": client_guid
        })

    def set_custom_field(self, client_guid, field_id, value):
        """Write a single custom field value on a client.
        field_id: GUID from SAP Static ID Reference (sap_static_ids rule)
        value: string value to set

        KLD field IDs (from static ID reference):
          Gate Code:    54d0db23-5570-48a8-9401-09ff9fbacc08
          Turf SF:      8a707d5d-f25c-44bd-8408-0a01e234849f
          Mow Day:      6ea5da5c-8281-44f6-b201-9d470076d354
          Master Note:  184a60a5-7c14-4967-8654-14a119000b60
          Has Irrig:    1ffcd0ee-04f5-475d-bfba-d3f612abf4c0
          No Notice:    af0a04c0-0e46-4fb8-b4ba-5bde3de39144
        """
        return self.sap.post("/WebServices/ClientViewWs.asmx/SaveCustomFieldData", {
            "Data": {
                "CustomerID": client_guid,
                "CustomFieldID": field_id,
                "CustomFieldValue": value
            }
        })

    def set_custom_fields_bulk(self, client_guid, fields):
        """Write multiple custom fields in one call.
        fields: list of {"CustomFieldID": "<guid>", "CustomFieldValue": "<value>"}
        """
        return self.sap.post("/WebServices/ClientViewWs.asmx/SaveCustomFieldData", {
            "Data": {
                "CustomerID": client_guid,
                "CustomFields": fields
            }
        })

    # ─── TAGS ─────────────────────────────────────────────────────────────────

    def get_tags(self, client_guid):
        """Tags applied to a client."""
        return self.sap.post_with_referer(
            "/webservices/TagsWs.asmx/GetSavedTagsList",
            {"InputData": {"ParentID": client_guid}},
            "/ClientView.aspx"
        )

    def add_tag(self, client_guid, tag_name):
        """Add a tag to a client."""
        return self.sap.post("/webservices/TagsWs.asmx/ModifyTag", {
            "TagData": {
                "TagParentID": client_guid,
                "TagParentType": "1",
                "TagValue": tag_name,
                "Operation": "add"
            }
        })

    def remove_tag(self, client_guid, tag_name):
        """Remove a tag from a client."""
        return self.sap.post("/webservices/TagsWs.asmx/ModifyTag", {
            "TagData": {
                "TagParentID": client_guid,
                "TagParentType": "1",
                "TagValue": tag_name,
                "Operation": "remove"
            }
        })

    # ─── CONTACTS ─────────────────────────────────────────────────────────────

    def save_contact(self, contact_data):
        """Save/create a contact on a client.
        contact_data: {CustomerID, FirstName, LastName, Email, Phone, ...}
        """
        return self.sap.post("/WebServices/ClientViewWs.asmx/SaveContact", {
            "ContactData": contact_data
        })

    def delete_contact(self, contact_guid):
        """Delete a contact by GUID."""
        return self.sap.post("/WebServices/ClientViewWs.asmx/DeleteContact", {
            "contactId": contact_guid
        })

    # ─── CREATE / UPDATE CLIENT ───────────────────────────────────────────────

    def get_edit_template(self):
        """Return a blank SaveClient payload with KLD defaults pre-filled.
        Populate FirstName, LastName, Address, City, PostalCode, MapCode, etc.
        Pass NULL_GUID as ClientID to create a new client.

        BILLING PROTECTION: Never add CC fields to this payload.
        """
        from datetime import date
        today = date.today()
        return {
            "ClientID": NULL_GUID,           # NULL_GUID = create, real GUID = update
            "IsLead": False,
            "saveType": 0,
            "IsConvertingLead": False,
            "FirstName": "",
            "LastName": "",
            "NickName": "",
            "ClientCompanyName": "",
            "Email": "",
            "HomePhone": "",
            "CellPhone": "",
            "ProviderID": NULL_GUID,
            "WorkPhone": "",
            "OtherPhone": "",
            "FaxNumber": "",
            "PreferredPhoneID": "3",          # 3 = Home
            "ClientTitle": "",
            "ListID": ACTIVE_LIST_ID,
            "QboID": "",
            "PropertyName": "",
            "PropertyNameAttentionTo": "",
            "Address": "",
            "AddressTwo": "",
            "City": "Cranbrook",
            "StateID": BC_STATE_ID,
            "PostalCode": "",
            "MapCode": "",
            "DivisionID": NULL_GUID,
            "NameOnInv": "",
            "AttentionTo": "",
            "BillingAddress": "",
            "BillingAddressTwo": "",
            "BillingCity": "Cranbrook",
            "BillingStateID": BC_STATE_ID,
            "BillingPostalCode": "",
            "SalesTaxRefID": NULL_GUID,
            "MasterPropertyClientID": NULL_GUID,
            "CountryID": CANADA_COUNTRY,
            "DefaultBillingUnderID": NULL_GUID,
            "ClientSinceDate": {"Month": today.month, "Day": today.day, "Year": today.year},
            "CSRId": NULL_GUID,
            "AccountTypeID": NULL_GUID,
            "PriorityID": "00000",
            "UserName": "",
            "Password": "",
            "Latitude": 49.5068,
            "Longitude": -115.7595,
            "SalesPersonID": NULL_GUID,
            "CustomerSourceID": NULL_GUID,
            "ReferredByID": NULL_GUID,
            "DoNotMarket": False,
            "BillingEmail": "",
            "FlagForReview": False,
            "AccountNumber": "",
            "SubscriptionType": "0",
            "BillingDate": {"Month": -1, "Day": -1, "Year": -1},
            "AutoCharge": False,
            "BillingNotes": "",
            "PaymentMethodID": DEFAULT_PAYMENT,
            "SalesTaxCodeID": SALES_TAX_CODE,
            "InvoiceFrequencyID": "1",
            "StandardTermID": STANDARD_TERM,
            "SendInvoiceBy": "Email",
            "DefaultInvoiceFormatID": NULL_GUID,
            "OfficeNotes": "",
            "CustomerType": "1",
            "CustomFields": [],
            "FormResponseID": NULL_GUID,
            "ClientPortalEnabled": False,
            "Geocode": False,
            "ManualGeocode": False,
            "UpdateManualGeocodeFlag": False
        }

    def save(self, client_info):
        """Create or update a client.
        client_info: dict matching the SaveClient payload shape (use get_edit_template()).
        Pass NULL_GUID as ClientID to create new. Pass real GUID to update.

        Returns: {CustomerID, ReturnURL, Errors}
        On create: real GUID is parsed from ReturnURL:
          ClientView.aspx?rk=<new-guid>&type=client&saved=client

        BILLING PROTECTION: NEVER include CC fields in client_info.
        """
        return self.sap.post("/webservices/ClientEditOverlayWs.asmx/SaveClient", {
            "info": client_info
        })

    def create(self, first_name, last_name, address, city="Cranbrook", postal_code="",
               map_code="", phone="", email="", is_lead=False, office_notes="",
               custom_fields=None):
        """Convenience: create a new client with minimal required fields.
        Returns: {CustomerID, ReturnURL, Errors}
        Parse the new GUID from ReturnURL: rk=<guid>
        """
        template = self.get_edit_template()
        full_name = f"{last_name}, {first_name}"
        template.update({
            "FirstName": first_name,
            "LastName": last_name,
            "ClientCompanyName": full_name,
            "PropertyName": full_name,
            "NameOnInv": full_name,
            "Address": address,
            "BillingAddress": address,
            "City": city,
            "BillingCity": city,
            "PostalCode": postal_code,
            "BillingPostalCode": postal_code,
            "MapCode": map_code,
            "HomePhone": phone,
            "Email": email,
            "IsLead": is_lead,
            "OfficeNotes": office_notes,
            "CustomFields": custom_fields or []
        })
        return self.save(template)

    def update(self, client_guid, **kwargs):
        """Update specific fields on an existing client.
        Fetches current data first, merges kwargs, then saves.
        kwargs: any field from the SaveClient payload shape.
        BILLING PROTECTION: billing/CC fields in kwargs will raise ValueError.
        """
        BLOCKED_FIELDS = {
            "CCFirstName", "CCLastName", "CCNumber", "CCToken", "CCCustomerToken",
            "CreditCards", "SavedCards", "PaymentMethods", "ACHAccounts",
            "AutoPay", "AutoPayEnabled", "AutoPayMethodID", "BillingCard",
            "CardOnFile", "StoredPayment", "DefaultPaymentMethod",
            "CreditCardNumber", "CreditCardExpiry"
        }
        blocked = BLOCKED_FIELDS & set(kwargs.keys())
        if blocked:
            raise ValueError(f"BILLING PROTECTION: Cannot update fields: {blocked}")

        # Fetch current data
        current = self.get_edit_info(client_guid)
        if isinstance(current, dict) and "d" in current:
            current = current["d"]

        # Merge changes
        current.update(kwargs)
        current["ClientID"] = client_guid
        return self.save(current)

    def convert_lead(self, customer_id):
        """Convert a lead to a full client.
        customer_id: the lead's CustomerID GUID
        NOTE: CustomerID must be at TOP LEVEL (not nested in InputData).
        Returns: {LeadName, Errors}
        """
        return self.sap.post("/webservices/QuoteWs.asmx/ConvertLead", {
            "InputData": {},
            "CustomerID": customer_id
        })

    # ─── SERVICES / JOBS ─────────────────────────────────────────────────────

    def pause_service(self, service_guid):
        """Pause an active service."""
        return self.sap.post("/WebServices/ClientViewWs.asmx/ToggleService", {
            "ServiceID": service_guid, "State": "pause"
        })

    def resume_service(self, service_guid):
        """Resume a paused service."""
        return self.sap.post("/WebServices/ClientViewWs.asmx/ToggleService", {
            "ServiceID": service_guid, "State": "restart"
        })

    def cancel_service(self, service_guid):
        """Cancel/delete a service."""
        return self.sap.post("/WebServices/ClientViewWS.asmx/CancelService", {
            "ServiceID": service_guid
        })

    def get_default_service_rate(self, client_guid, service_type_id):
        """Get default rate for a service type on a client.
        Uses ClientUpdateWs.
        """
        return self.sap.post("/webservices/ClientUpdateWs.asmx/GetDefaultServiceRate", {
            "CustomerID": client_guid,
            "ServiceTypeID": service_type_id
        })

    def get_last_service_data(self, client_guid, service_type_id):
        """Get data from the last time a service type was performed for this client."""
        return self.sap.post("/webservices/ClientUpdateWs.asmx/GetLastServiceData", {
            "CustomerID": client_guid,
            "ServiceTypeID": service_type_id
        })

    # ─── NOTES / TODOS ────────────────────────────────────────────────────────

    def create_note(self, client_guid, note_text, subject="Note", created_by_id=None):
        """Create a ticket/note on a client (shortcut — delegates to TicketsAPI shape).
        For full ticket control use sap.tickets.create_on_client() instead.
        """
        from .sap_core import USER_ID
        return self.sap.post("/CRMBFF/TicketEdit/TicketEdit_Ticket_PostAsync", {
            "Ticket": {
                "CategoryID": None,
                "TicketStatus": 0,
                "EntityID": client_guid,
                "EntityType": "Account",
                "DueDate": "",
                "TicketDetail": {
                    "TicketEventType": 1,
                    "Subject": subject,
                    "Body": note_text,
                    "CreatedByID": created_by_id or USER_ID,
                    "CreatedByType": 1
                }
            }
        })

    def save_note(self, client_guid, note_text):
        """Save a note via ClientUpdateWs (lighter than full ticket create)."""
        return self.sap.post("/webservices/ClientUpdateWs.asmx/SaveNote", {
            "CustomerID": client_guid,
            "NoteText": note_text
        })

    def save_todo(self, client_guid, subject, body="", due_date="", assigned_to=None):
        """Save a to-do item on a client via ClientUpdateWs."""
        from .sap_core import USER_ID
        return self.sap.post("/webservices/ClientUpdateWs.asmx/SaveToDo", {
            "CustomerID": client_guid,
            "Subject": subject,
            "Body": body,
            "DueDate": due_date,
            "AssignedUserID": assigned_to or USER_ID
        })

    # ─── PORTAL ───────────────────────────────────────────────────────────────

    def send_portal_invite(self, client_guid):
        """Send a client portal invite email."""
        return self.sap.post("/WebServices/ClientViewWs.asmx/SendClientPortalInviteEmail", {
            "customerId": client_guid
        })

    # ─── HELPERS ─────────────────────────────────────────────────────────────

    def get_full_profile(self, client_guid):
        """Convenience: fetch the most common data points for a client in one shot.
        Returns dict with keys: core, contacts, properties, services, custom_fields, tags.
        Makes 6 API calls — use only when you need full context.
        """
        core = self.get(client_guid)
        return {
            "core": core,
            "contacts": self.get_contacts(client_guid),
            "properties": self.get_properties(client_guid),
            "services": self.get_all_services(client_guid),
            "custom_fields": self.get_custom_fields(client_guid),
            "tags": self.get_tags(client_guid)
        }

    def find_one(self, term):
        """Search and return the first matching client record."""
        results = self.search(term)
        if isinstance(results, list) and results:
            return results[0]
        if isinstance(results, dict):
            items = results.get("d") or results.get("Results") or []
            if items:
                return items[0]
        return None


# Convenience functions (backward compat)
def search_clients(term):
    return ClientsAPI().search(term)

def get_client(guid):
    return ClientsAPI().get(guid)
