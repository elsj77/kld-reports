"""
sap_vendors.py — Vendor Operations
Endpoints: VendorsWs (32 ops, WSDL-confirmed)
"""
from .sap_core import SAPClient, get_sap, NULL_GUID

class VendorsAPI:
    def __init__(self, sap=None):
        self.sap = sap or get_sap()
    
    def get_all(self):
        """List all vendors."""
        return self.sap.post("/v3/WebServices/Team/VendorsWs.asmx/GetVendors", {})
    
    def get(self, vendor_id):
        """Get single vendor data."""
        return self.sap.post("/v3/WebServices/Team/VendorsWs.asmx/GetVendorData", {"VendorID": vendor_id})
    
    def save(self, vendor_data):
        """Create/update vendor."""
        return self.sap.post("/v3/WebServices/Team/VendorsWs.asmx/SaveVendor", vendor_data)
    
    def update_status(self, vendor_ids, status):
        """Update vendor status."""
        return self.sap.post("/v3/WebServices/Team/VendorsWs.asmx/UpdateVendorStatus", {"VendorIDs": vendor_ids, "Status": status})
    
    def delete(self, vendor_ids):
        """Delete vendors."""
        return self.sap.post("/v3/WebServices/Team/VendorsWs.asmx/DeleteVendors", {"VendorIDs": vendor_ids})
    
    def get_schedule(self, vendor_id):
        """Get vendor's resource schedule."""
        return self.sap.post("/v3/WebServices/Team/VendorsWs.asmx/GetResourceSchedule", {"VendorID": vendor_id})
    
    def save_scheduled_day(self, day_data):
        """Save scheduled day."""
        return self.sap.post("/v3/WebServices/Team/VendorsWs.asmx/SaveScheduledDay", day_data)
    
    def save_schedule_override(self, override_data):
        """Save schedule override."""
        return self.sap.post("/v3/WebServices/Team/VendorsWs.asmx/SaveScheduledDayOverride", override_data)
    
    def get_damage_cases(self, vendor_id):
        """Get vendor damage cases."""
        return self.sap.post("/v3/WebServices/Team/VendorsWs.asmx/GetVendorDamageCases", {"VendorID": vendor_id})
    
    def get_rating(self, vendor_id):
        """Get vendor rating."""
        return self.sap.post("/v3/WebServices/Team/VendorsWs.asmx/GetVendorRating", {"VendorID": vendor_id})
    
    def get_time_off(self, vendor_id):
        """Get vendor time off."""
        return self.sap.post("/v3/WebServices/Team/VendorsWs.asmx/GetVendorTimeOff", {"VendorID": vendor_id})
    
    def get_avatar(self, vendor_id):
        """Get vendor avatar."""
        return self.sap.post("/v3/WebServices/Team/VendorsWs.asmx/GetVendorAvatar", {"VendorID": vendor_id})
    
    def save_note(self, note_data):
        """Save note on vendor."""
        return self.sap.post("/v3/WebServices/Team/VendorsWs.asmx/SaveNoteItem", note_data)
    
    def delete_note(self, note_guid):
        """Delete note."""
        return self.sap.post("/v3/WebServices/Team/VendorsWs.asmx/DeleteNoteItem", {"NoteID": note_guid})
