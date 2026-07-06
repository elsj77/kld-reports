"""
SAP Service Update Module — Update existing services without creating duplicates.

CRACKED PATTERN (2026-07-02):
Each Save* endpoint has a specific field that controls UPDATE vs CREATE.
Setting it to the existing service ID = UPDATE. Setting to NULL_GUID = CREATE.

| Job Type     | Save Endpoint              | Update Key  | Notes                              |
|--------------|----------------------------|-------------|-------------------------------------|
| Recurring    | SaveRecurringService       | ServiceID   | Keep raw GetPanelData structure     |
| Package      | SavePackage                | PackageID   | Use builder-format Services[]       |
| OneTime      | SaveOneTimeService         | ServiceID   | Use builder-format ServiceDetails   |
| WaitingList  | SaveWaitingListService     | ServiceID   | Use builder-format ServiceDetails   |

CRITICAL: For Package, BOTH PackageID AND ServiceID must be set to existing ID.
          Setting only ServiceID (with PackageID=NULL_GUID) creates a DUPLICATE.

Usage:
    from modules.sap_service_update import ServiceUpdater
    updater = ServiceUpdater(sap)
    
    # Update mowing budgeted hours
    updater.update_recurring(mow_service_id, hours=0.58, budgeted_men=2)
    
    # Update FW package rounds
    updater.update_package(fw_package_id, hours=0.15, budgeted_men=1)
    
    # Update one-time service
    updater.update_onetime(service_id, hours=0.30, budgeted_men=1)
    
    # Update waiting list service
    updater.update_waiting_list(service_id, hours=0.5, budgeted_men=2)
"""

import json, re, copy
from datetime import date

NULL_GUID = '00000000-0000-0000-0000-000000000000'


def _clean_types(obj):
    """Recursively remove __type fields from nested dicts/lists."""
    if isinstance(obj, dict):
        obj.pop('__type', None)
        for v in obj.values():
            _clean_types(v)
    elif isinstance(obj, list):
        for item in obj:
            _clean_types(item)


def _fix_browser_date(d):
    """Convert a BrowserDate dict to clean format. Invalid dates -> {-1,-1,-1}."""
    if d is None or not isinstance(d, dict):
        return {'Month': -1, 'Day': -1, 'Year': -1}
    if not d.get('IsValid', False):
        return {'Month': -1, 'Day': -1, 'Year': -1}
    return {'Month': d['Month'], 'Day': d['Day'], 'Year': d['Year']}


class ServiceUpdater:
    """Update existing SAP services without creating duplicates."""
    
    def __init__(self, sap_client):
        self.sap = sap_client
        self._get_panel = lambda sid: self._unwrap(self.sap.post(
            '/WebServices/ServiceEditorWs.asmx/GetPanelData',
            {'Input': {'ServiceID': sid, 'Ticket': NULL_GUID}}
        ))
    
    def _unwrap(self, result):
        d = result.get('d', result) if isinstance(result, dict) else result
        if isinstance(d, str):
            d = json.loads(d)
        return d
    
    def _add_common_fields(self, d, service_id, user_id, job_id):
        """Add fields required for save that GetPanelData doesn't return."""
        d['UserID'] = user_id
        d['JobID'] = job_id
        d['ServiceID'] = service_id
        d['CommissionOverrideData'] = {'CommissionIDs': [], 'ResourceTypeIDs': [], 'AmountList': []}
        d['CreateNewProject'] = False
        d['IsForProject'] = False
        d['ProjectID'] = NULL_GUID
        d['QuoteID'] = NULL_GUID
        d['Assets'] = []
    
    def _get_customer_job_id(self, customer_id):
        """Get CustomerJobID for a client."""
        result = self.sap.post('/WebServices/ClientViewWs.asmx/GetCustomerData', {
            'customerId': customer_id
        })
        d = self._unwrap(result)
        client = d.get('Client', {})
        return client.get('CustomerJobID', NULL_GUID)
    
    def _get_running_service_ids(self, customer_id, customer_job_id):
        """Get set of currently running service IDs for duplicate detection."""
        try:
            result = self.sap.post('/WebServices/ClientViewWs.asmx/GetAllServicesAsync', {
                'request': {
                    'CustomerID': customer_id,
                    'AllJobs': True, 'Start': 0, 'Total': 50, 'ShowMore': False,
                    'CustomerJobID': customer_job_id,
                    'IncludeCancelled': True, 'GetAll': True
                }
            })
            d = self._unwrap(result)
            jobs = d.get('Result', d).get('Jobs', [])
            return {j['ID'] for j in jobs if j.get('StateHelp') == 'Running'}
        except:
            return set()
    
    def _check_duplicates(self, customer_id, customer_job_id, before_ids):
        """Check for and auto-cancel newly created duplicate services."""
        try:
            result = self.sap.post('/WebServices/ClientViewWs.asmx/GetAllServicesAsync', {
                'request': {
                    'CustomerID': customer_id,
                    'AllJobs': True, 'Start': 0, 'Total': 50, 'ShowMore': False,
                    'CustomerJobID': customer_job_id,
                    'IncludeCancelled': True, 'GetAll': True
                }
            })
            d = self._unwrap(result)
            jobs = d.get('Result', d).get('Jobs', [])
            running = {j['ID'] for j in jobs if j.get('StateHelp') == 'Running'}
            new_ids = running - before_ids
            for nid in new_ids:
                self.sap.post('/WebServices/ClientViewWs.asmx/CancelService', {'ServiceID': nid})
            return new_ids
        except:
            return set()
    
    
    def _preserve_route_sheet_notes(self, notes):
        """Clean and preserve existing RouteSheetNotes from panel data."""
        if not notes:
            return []
        preserved = []
        for note in notes:
            clean_note = {}
            for k, v in note.items():
                if k == '__type':
                    continue
                if isinstance(v, dict):
                    clean_note[k] = _fix_browser_date(v)
                else:
                    clean_note[k] = v
            preserved.append(clean_note)
        return preserved
    
    def update_recurring(self, service_id, hours=None, budgeted_men=None, 
                         user_id=None, job_id=None):
        """
        Update a recurring service's Hours and/or BudgetedNumberOfMen.
        Uses the raw GetPanelData structure (same pattern verified working 2026-07-02).
        
        Returns: dict with success, errors, changes, duplicate_ids.
        """
        from modules.sap_core import USER_ID, JOB_ID
        uid = user_id or USER_ID
        jid = job_id or JOB_ID
        
        d = self._get_panel(service_id)
        panel_type = d.get('__type', '')
        if 'Recurring' not in panel_type:
            return {'success': False, 'errors': [f'Not a recurring service: {panel_type}']}
        
        customer_id = d.get('CustomerID', '')
        customer_job_id = self._get_customer_job_id(customer_id)
        before_ids = self._get_running_service_ids(customer_id, customer_job_id)
        
        # Modify target fields in Service.Details[]
        details = d.get('Service', {}).get('Details', [])
        changes = []
        for detail in details:
            old_hours = detail.get('Hours')
            old_men = detail.get('BudgetedNumberOfMen')
            if hours is not None:
                detail['Hours'] = hours
            if budgeted_men is not None:
                detail['BudgetedNumberOfMen'] = budgeted_men
            changes.append({
                'name': detail.get('ServiceName', ''),
                'hours': (old_hours, detail.get('Hours')),
                'men': (old_men, detail.get('BudgetedNumberOfMen')),
            })
        
        # Add required fields
        self._add_common_fields(d, service_id, uid, jid)
        
        # Fix BrowserDate fields
        for detail in details:
            for date_field in ['EndDate', 'DiscountExpiration', 'StartDate', 'InitialDate']:
                if date_field in detail:
                    detail[date_field] = _fix_browser_date(detail[date_field])
        if 'DateSold' in d:
            d['DateSold'] = _fix_browser_date(d['DateSold'])
        
        # Clean
        _clean_types(d)
        d.pop('CallStack', None)
        d.pop('Errors', None)
        
        # Save
        result = self.sap.post('/WebServices/ServiceEditorWs.asmx/SaveRecurringService', {'Input': d})
        d2 = self._unwrap(result)
        errors = d2.get('Errors', [])
        
        dup_ids = self._check_duplicates(customer_id, customer_job_id, before_ids) if not errors else set()
        
        return {
            'success': not errors and not dup_ids,
            'errors': errors,
            'changes': changes,
            'duplicate_ids': list(dup_ids),
        }
    
    def update_package(self, service_id, hours=None, budgeted_men=None,
                       user_id=None, job_id=None):
        """
        Update a package's service round Hours and/or BudgetedNumberOfMen.
        
        KEY: Must set PackageID = existing ID (not NULL_GUID) to UPDATE, not CREATE.
        Must use builder-format Services[] (no Start/End string dates from panel).
        Verified working 2026-07-02.
        """
        from modules.sap_core import USER_ID, JOB_ID
        uid = user_id or USER_ID
        jid = job_id or JOB_ID
        
        d = self._get_panel(service_id)
        panel_type = d.get('__type', '')
        if 'Package' not in panel_type:
            return {'success': False, 'errors': [f'Not a package: {panel_type}']}
        
        customer_id = d.get('CustomerID', '')
        customer_job_id = self._get_customer_job_id(customer_id)
        before_ids = self._get_running_service_ids(customer_id, customer_job_id)
        
        # Convert Services[] to builder format (avoids Start/End string date null refs)
        panel_services = d.get('Services', [])
        save_services = []
        changes = []
        for svc in panel_services:
            svc_id = svc.get('ServiceID', NULL_GUID)
            name_clean = re.sub('<[^>]+>', '', svc.get('ServiceName', '')).strip()
            old_hours = svc.get('Hours')
            old_men = svc.get('BudgetedNumberOfMen')
            
            save_services.append({
                'ID': svc_id,  # EXISTING round ServiceID
                'Description': svc.get('Description', name_clean),
                'Rate': float(svc.get('Rate', 0) or 0),  # PRESERVE
                'Quantity': float(svc.get('Quantity', 1) or 1),
                'Hours': hours if hours is not None else float(svc.get('Hours', 0) or 0),
                'BudgetedNumberOfMen': budgeted_men if budgeted_men is not None else int(svc.get('BudgetedNumberOfMen', 1) or 1),
                'NumberOfDays': int(svc.get('NumberOfDays', 1) or 1),
                'AddToSchedule': svc.get('ShowAddToSchedule', False),
                'IsActive': svc.get('IsActive', True),
                'Products': svc.get('Products', []),
                'InstalledProducts': svc.get('InstalledProducts', []),
                'DiscountID': svc.get('DiscountID', NULL_GUID),
                'DiscountType': int(svc.get('DiscountType', 0) or 0),
                'DiscountAmount': float(svc.get('DiscountAmount', 0) or 0),  # PRESERVE
                'DiscountExpiration': {'Month': -1, 'Day': -1, 'Year': -1},
                'QuoteLineItemID': svc.get('QuoteLineItemID', NULL_GUID),
            })
            changes.append({
                'name': name_clean,
                'hours': (old_hours, save_services[-1]['Hours']),
                'men': (old_men, save_services[-1]['BudgetedNumberOfMen']),
                'rate': save_services[-1]['Rate'],
            })
        
        # Build save payload in builder format
        save_payload = {'Input': {
            'UserID': uid, 'JobID': jid,
            'CustomerID': customer_id,
            'CustomerSourceID': d.get('CustomerSourceID', NULL_GUID),
            'ContractID': d.get('ContractID', NULL_GUID),
            'ServiceID': service_id,
            'PackageID': service_id,  # KEY: prevents duplicate creation
            'SalesPersonID': d.get('SalesPersonID', NULL_GUID),
            'CSRID': d.get('CSRID', NULL_GUID),
            'InvoiceFreq': d.get('InvoiceFrequency', 1),
            'InvoiceAsWorkOrder': d.get('InvoiceAsWorkOrder', False),
            'PaymentType': d.get('PaymentType', 2),
            'CallAhead': d.get('CallAhead', False),
            'ArrivalWindow': d.get('ArrivalWindow', 0),
            'DontApplyMinimumAmount': d.get('DontApplyMinimumAmount', False),
            'UseAnnualPricing': d.get('UseAnnualPricing', False),
            'PONumber': d.get('PONumber', ''),
            'DateSold': _fix_browser_date(d.get('DateSold')),
            'WorkOrderNumber': d.get('WorkOrderNumber', ''),
            'AreaTreatedIDs': d.get('AreaTreatedIDs', []),
            'GroupJobs': d.get('GroupJobs', False),
            'GroupName': d.get('GroupName', ''),
            'IncludeSunday': d.get('IncludeSunday', True),
            'IncludeMonday': d.get('IncludeMonday', True),
            'IncludeTuesday': d.get('IncludeTuesday', True),
            'IncludeWednesday': d.get('IncludeWednesday', True),
            'IncludeThursday': d.get('IncludeThursday', True),
            'IncludeFriday': d.get('IncludeFriday', True),
            'IncludeSaturday': d.get('IncludeSaturday', True),
            'MaximumManHoursPerDay': d.get('MaximumManHoursPerDay', '9'),
            'CommissionOverrideData': {'CommissionIDs': [], 'ResourceTypeIDs': [], 'AmountList': []},
            'CommissionType': d.get('CommissionType', 0),
            'InternalNote': d.get('InternalNote', ''),
            'ShowInternalNoteRow': d.get('ShowInternalNoteRow', True),
            'SelectedPackageID': d.get('SelectedPackageID', NULL_GUID),
            'RenewalOption': d.get('RenewalOption', 2),
            'AssignedResourceIDs': d.get('AssignedResourceIDs', []),
            'RenewPackage': False,
            'ExcludeSunday': d.get('ExcludeSunday', False),
            'ExcludeMonday': d.get('ExcludeMonday', False),
            'ExcludeTuesday': d.get('ExcludeTuesday', False),
            'ExcludeWednesday': d.get('ExcludeWednesday', False),
            'ExcludeThursday': d.get('ExcludeThursday', False),
            'ExcludeFriday': d.get('ExcludeFriday', False),
            'ExcludeSaturday': d.get('ExcludeSaturday', False),
            'Services': save_services,
            'RouteSheetNotes': self._preserve_route_sheet_notes(d.get('RouteSheetNotes', [])),
            'ServiceItems': {'Assets': []},
        }}
        
        result = self.sap.post('/WebServices/ServiceEditorWs.asmx/SavePackage', save_payload)
        d2 = self._unwrap(result)
        errors = d2.get('Errors', [])
        
        dup_ids = self._check_duplicates(customer_id, customer_job_id, before_ids) if not errors else set()
        
        return {
            'success': not errors and not dup_ids,
            'errors': errors,
            'changes': changes,
            'duplicate_ids': list(dup_ids),
        }
    
    def update_onetime(self, service_id, hours=None, budgeted_men=None,
                       user_id=None, job_id=None):
        """
        Update a one-time service's Hours and/or BudgetedNumberOfMen.
        Uses builder-format ServiceDetails[{Detail: {...}}].
        Pattern: ServiceID = existing ID for update (same as recurring).
        """
        from modules.sap_core import USER_ID, JOB_ID
        uid = user_id or USER_ID
        jid = job_id or JOB_ID
        
        d = self._get_panel(service_id)
        panel_type = d.get('__type', '')
        if 'OneTime' not in panel_type:
            return {'success': False, 'errors': [f'Not a one-time service: {panel_type}']}
        
        customer_id = d.get('CustomerID', '')
        customer_job_id = self._get_customer_job_id(customer_id)
        before_ids = self._get_running_service_ids(customer_id, customer_job_id)
        
        # Convert ServiceDetails to builder format
        panel_details = d.get('ServiceDetails', [])
        save_details = []
        changes = []
        for item in panel_details:
            sd = item.get('ServiceDetail', item.get('Detail', {}))
            old_hours = sd.get('Hours')
            old_men = sd.get('BudgetedNumberOfMen')
            
            new_detail = {
                'ID': sd.get('ID', NULL_GUID),
                'ServiceTypeID': sd.get('ServiceTypeID', ''),
                'ServiceName': sd.get('ServiceName', ''),
                'StartDate': _fix_browser_date(sd.get('StartDate')),
                'EndDate': _fix_browser_date(sd.get('EndDate')),
                'StartTime': sd.get('StartTime', ''),
                'EndTime': sd.get('EndTime', ''),
                'AssignedResourceIDs': sd.get('AssignedResourceIDs', []),
                'Quantity': float(sd.get('Quantity', 1) or 1),
                'Rate': float(sd.get('Rate', 0) or 0),  # PRESERVE
                'Hours': hours if hours is not None else float(sd.get('Hours', 0) or 0),
                'BudgetedNumberOfMen': budgeted_men if budgeted_men is not None else int(sd.get('BudgetedNumberOfMen', 1) or 1),
                'NumberOfDays': int(sd.get('NumberOfDays', 1) or 1),
                'InvoiceNotes': sd.get('InvoiceNotes', ''),  # PRESERVE invoice description
                'RouteSheetNote': sd.get('RouteSheetNote', ''),  # PRESERVE route sheet note
                'RouteSheetNotes': [],
                'Products': [],
                'InstalledProducts': [],
                'Appointments': [],
                'BudgetedHourOverrides': [],
                'ServiceMode': sd.get('ServiceMode', ''),
                'Status': sd.get('Status', 1),
                'DiscountID': sd.get('DiscountID', NULL_GUID),
                'DiscountType': int(sd.get('DiscountType', 0) or 0),
                'DiscountAmount': float(sd.get('DiscountAmount', 0) or 0),
                'DiscountExpiration': {'Month': -1, 'Day': -1, 'Year': -1},
                'QuoteLineItemID': sd.get('QuoteLineItemID', NULL_GUID),
                'ProductsRate': float(sd.get('ProductsRate', 0) or 0),
            }
            
            save_details.append({
                'Detail': new_detail,
                'Products': [],
                'InstalledProducts': [],
                'BudgetedHourOverrides': [],
                'Appointments': [],
            })
            changes.append({
                'name': sd.get('ServiceName', ''),
                'hours': (old_hours, new_detail['Hours']),
                'men': (old_men, new_detail['BudgetedNumberOfMen']),
            })
        
        self._add_common_fields(d, service_id, uid, jid)
        d['ServiceDetails'] = save_details
        d['ServiceTypeID'] = d.get('ServiceTypeID', '')
        d['IsComplete'] = d.get('IsComplete', False)
        d['PushMultidayAssignments'] = False
        
        if 'DateSold' in d:
            d['DateSold'] = _fix_browser_date(d['DateSold'])
        
        _clean_types(d)
        d.pop('CallStack', None)
        d.pop('Errors', None)
        
        result = self.sap.post('/WebServices/ServiceEditorWs.asmx/SaveOneTimeService', {'Input': d})
        d2 = self._unwrap(result)
        errors = d2.get('Errors', [])
        
        dup_ids = self._check_duplicates(customer_id, customer_job_id, before_ids) if not errors else set()
        
        return {
            'success': not errors and not dup_ids,
            'errors': errors,
            'changes': changes,
            'duplicate_ids': list(dup_ids),
        }
    
    def update_waiting_list(self, service_id, hours=None, budgeted_men=None,
                            user_id=None, job_id=None):
        """
        Update a waiting list service's Hours and/or BudgetedNumberOfMen.
        Uses builder-format ServiceDetails[{Detail: {...}}].
        
        WARNING: Don't include RenewServices field (causes System.Boolean error).
        """
        from modules.sap_core import USER_ID, JOB_ID
        uid = user_id or USER_ID
        jid = job_id or JOB_ID
        
        d = self._get_panel(service_id)
        panel_type = d.get('__type', '')
        if 'WaitingList' not in panel_type:
            return {'success': False, 'errors': [f'Not a waiting list service: {panel_type}']}
        
        customer_id = d.get('CustomerID', '')
        customer_job_id = self._get_customer_job_id(customer_id)
        before_ids = self._get_running_service_ids(customer_id, customer_job_id)
        
        panel_details = d.get('ServiceDetails', [])
        save_details = []
        changes = []
        for item in panel_details:
            sd = item.get('ServiceDetail', item.get('Detail', {}))
            old_hours = sd.get('Hours')
            old_men = sd.get('BudgetedNumberOfMen')
            
            new_detail = {
                'ID': sd.get('ID', NULL_GUID),
                'ServiceTypeID': sd.get('ServiceTypeID', d.get('ServiceTypeID', '')),
                'ServiceName': sd.get('ServiceName', d.get('ServiceType', '')),
                'StartDate': _fix_browser_date(sd.get('StartDate')),
                'EndDate': _fix_browser_date(sd.get('EndDate')),
                'AssignedResourceIDs': sd.get('AssignedResourceIDs', []),
                'Quantity': float(sd.get('Quantity', 1) or 1),
                'Rate': float(sd.get('Rate', 0) or 0),  # PRESERVE
                'Hours': hours if hours is not None else float(sd.get('Hours', 0) or 0),
                'BudgetedNumberOfMen': budgeted_men if budgeted_men is not None else int(sd.get('BudgetedNumberOfMen', 1) or 1),
                'NumberOfDays': int(sd.get('NumberOfDays', 1) or 1),
                'InvoiceNotes': sd.get('InvoiceNotes', ''),  # PRESERVE invoice description
                'RouteSheetNote': sd.get('RouteSheetNote', ''),  # PRESERVE route sheet note
                'RouteSheetNotes': [],
                'Products': [],
                'InstalledProducts': [],
                'Appointments': [],
                'BudgetedHourOverrides': [],
                'ServiceMode': sd.get('ServiceMode', ''),
                'Status': sd.get('Status', 1),
                'DiscountID': sd.get('DiscountID', NULL_GUID),
                'DiscountType': int(sd.get('DiscountType', 0) or 0),
                'DiscountAmount': float(sd.get('DiscountAmount', 0) or 0),
                'DiscountExpiration': {'Month': -1, 'Day': -1, 'Year': -1},
                'QuoteLineItemID': sd.get('QuoteLineItemID', NULL_GUID),
                'ProductsRate': float(sd.get('ProductsRate', 0) or 0),
            }
            
            save_details.append({
                'Detail': new_detail,
                'Products': [],
                'InstalledProducts': [],
                'BudgetedHourOverrides': [],
                'Appointments': [],
            })
            changes.append({
                'name': sd.get('ServiceName', ''),
                'hours': (old_hours, new_detail['Hours']),
                'men': (old_men, new_detail['BudgetedNumberOfMen']),
            })
        
        self._add_common_fields(d, service_id, uid, jid)
        d['ServiceDetails'] = save_details
        d['ServiceTypeID'] = d.get('ServiceTypeID', '')
        d['CustomPackageID'] = d.get('CustomPackageID', NULL_GUID)
        d['IsRenewable'] = d.get('IsRenewable', False)
        d['RenewStartDate'] = _fix_browser_date(d.get('RenewStartDate'))
        d['RenewEndDate'] = _fix_browser_date(d.get('RenewEndDate'))
        d['PushMultidayAssignments'] = False
        # DO NOT include RenewServices - causes System.Boolean deserialization error
        
        if 'DateSold' in d:
            d['DateSold'] = _fix_browser_date(d['DateSold'])
        
        _clean_types(d)
        d.pop('CallStack', None)
        d.pop('Errors', None)
        
        result = self.sap.post('/WebServices/ServiceEditorWs.asmx/SaveWaitingListService', {'Input': d})
        d2 = self._unwrap(result)
        errors = d2.get('Errors', [])
        
        dup_ids = self._check_duplicates(customer_id, customer_job_id, before_ids) if not errors else set()
        
        return {
            'success': not errors and not dup_ids,
            'errors': errors,
            'changes': changes,
            'duplicate_ids': list(dup_ids),
        }
