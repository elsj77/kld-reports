"""sap_tags.py — Tag Operations. Endpoints: TagsWs (6 ops), MSTagsWs"""
from .sap_core import SAPClient, get_sap, NULL_GUID

class TagsAPI:
    def __init__(self, sap=None):
        self.sap = sap or get_sap()
    
    def get_all_tags(self):
        """All company tags. EntityType: 1=Client."""
        return self.sap.post("/webservices/ListsWs.asmx/GetAvailableTagsList", {"InputData": {"EntityType": 1}})
    
    def get_saved_tags(self, entity_guid):
        """Tags on a specific record."""
        return self.sap.post("/webservices/TagsWs.asmx/GetSavedTagsList", {"parentID": entity_guid})
    
    def add_tag(self, entity_guid, tag_name, entity_type="1"):
        """Add tag. EntityType: 1=Client, 2=Job."""
        return self.sap.post("/webservices/TagsWs.asmx/ModifyTag", {"TagData": {"TagParentID": entity_guid, "TagParentType": entity_type, "TagValue": tag_name, "Operation": "add"}})
    
    def remove_tag(self, entity_guid, tag_name, entity_type="1"):
        """Remove tag."""
        return self.sap.post("/webservices/TagsWs.asmx/ModifyTag", {"TagData": {"TagParentID": entity_guid, "TagParentType": entity_type, "TagValue": tag_name, "Operation": "remove"}})
    
    def get_categories(self):
        return self.sap.post("/webservices/TagsWs.asmx/GetAllTagCategories", {})
    
    def add_category(self, category_name):
        return self.sap.post("/webservices/TagsWs.asmx/AddCategory", {"CategoryName": category_name})
    
    def check_permission(self):
        return self.sap.post("/webservices/TagsWs.asmx/CheckTagsPermission", {})
