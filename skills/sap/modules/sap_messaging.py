"""sap_messaging.py — Messaging/SMS Operations. Endpoints: MessagingWs (22 ops)"""
from .sap_core import SAPClient, get_sap, NULL_GUID

class MessagingAPI:
    def __init__(self, sap=None):
        self.sap = sap or get_sap()
    
    def get_recent_messages(self, start=0, end=15, direction=1):
        return self.sap.post("/WebServices/MessagingWs.asmx/GetRecentMessage", {"Input": {"Direction": direction, "StartIndex": start, "EndIndex": end}})
    
    def get_message_thread(self, thread_id):
        return self.sap.post("/WebServices/MessagingWs.asmx/GetMessageThread", {"Input": {"ThreadID": thread_id}})
    
    def get_archived_thread(self, thread_id):
        return self.sap.post("/WebServices/MessagingWs.asmx/GetArchivedMessageThread", {"Input": {"ThreadID": thread_id}})
    
    def send_text(self, customer_id, phone, message):
        return self.sap.post("/WebServices/MessagingWs.asmx/SendTextMessage", {"Input": {"CustomerID": customer_id, "PhoneNumber": phone, "Message": message}})
    
    def get_unread_count(self):
        """Get unread message count. Requires EntityID (user GUID)."""
        from .sap_core import USER_ID
        return self.sap.post_with_referer("/WebServices/MessagingWs.asmx/GetUnreadCount", {"EntityID": USER_ID}, "/v3/Marketing/MessageCenter")
    
    def search(self, search_term):
        return self.sap.post("/WebServices/MessagingWs.asmx/Search", {"Input": {"SearchString": search_term}})
    
    def mark_read(self, thread_id):
        return self.sap.post("/WebServices/MessagingWs.asmx/V3MarkAsRead", {"Input": {"ThreadID": thread_id}})
    
    def mark_unread(self, thread_id):
        return self.sap.post("/WebServices/MessagingWs.asmx/V3MarkAsUnread", {"Input": {"ThreadID": thread_id}})
    
    def remove_from_feed(self, thread_id):
        return self.sap.post("/WebServices/MessagingWs.asmx/V3RemoveFromFeed", {"Input": {"ThreadID": thread_id}})
    
    def get_response_templates(self):
        return self.sap.post("/WebServices/MessagingWs.asmx/GetResponseTemplateListWithNames", {})
    
    def load_template(self, template_id):
        return self.sap.post("/WebServices/MessagingWs.asmx/LoadTemplateText", {"Input": {"TemplateID": template_id}})
    
    def save_cell_phone(self, customer_id, phone):
        return self.sap.post("/WebServices/MessagingWs.asmx/SaveEntityCellPhoneNumber", {"Input": {"CustomerID": customer_id, "PhoneNumber": phone}})
    
    def two_way_enabled(self):
        return self.sap.post("/WebServices/MessagingWs.asmx/TwoWayTextMessageEnabled", {})
    
    def get_attachments(self, thread_id):
        return self.sap.post("/WebServices/MessagingWs.asmx/GetCurrentAttachments", {"Input": {"ThreadID": thread_id}})
