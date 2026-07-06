"""
sap_artifacts.py — File/Photo/Attachment Operations
Endpoints: ArtifactsWs (15 ops, WSDL-confirmed)

IMPORTANT: Two separate query paths:
  QueryAll / Query     → file-type attachments (PDFs, docs, non-photo uploads)
  QueryMobile          → property PHOTOS uploaded via mobile / FileUpload widget
                         Use this for client property photos.
  QueryNonMobile       → non-mobile (office-uploaded) files only
"""
from .sap_core import SAPClient, get_sap, NULL_GUID


class ArtifactsAPI:
    def __init__(self, sap=None):
        self.sap = sap or get_sap()

    # ─── QUERY ───────────────────────────────────────────────────────────────

    def query(self, entity_id, entity_type=1):
        """Query file attachments by entity.
        entity_type: 1=Client, 2=Job, 3=Employee, 4=Vendor
        Returns file-type attachments only (not mobile photos).
        """
        return self.sap.post("/WebServices/ArtifactsWs.asmx/Query", {
            "EntityID": entity_id,
            "EntityType": entity_type
        })

    def query_all(self, entity_id, mobile_only=False):
        """Query all artifacts for an entity.
        NOTE: Does NOT return photos uploaded via FileUpload/mobile — use query_mobile() for those.
        """
        return self.sap.post("/WebServices/ArtifactsWs.asmx/QueryAll", {
            "Data": {"ParentID": entity_id, "MobileOnly": mobile_only}
        })

    def query_mobile(self, entity_id, mobile_only=False):
        """Query mobile/photo artifacts — USE THIS for property photos.
        Returns: {Attachments: [{ArtifactID, FileName, FileDate, CDNUrl, ...}]}
        This is the correct endpoint for FileUpload-sourced photos.
        """
        return self.sap.post("/WebServices/ArtifactsWs.asmx/QueryMobile", {
            "Data": {"ParentID": entity_id, "MobileOnly": mobile_only}
        })

    def query_mobile_artifacts(self, entity_id):
        """Alternate mobile artifact query endpoint."""
        return self.sap.post("/WebServices/ArtifactsWs.asmx/QueryMobileArtifacts", {
            "EntityID": entity_id
        })

    def query_non_mobile(self, entity_id):
        """Query non-mobile (office-uploaded) files only."""
        return self.sap.post("/WebServices/ArtifactsWs.asmx/QueryNonMobileArtifacts", {
            "EntityID": entity_id
        })

    def query_attachments_paged(self, entity_id, start_row=1, max=25):
        """Query attachments with pagination (datablocked)."""
        return self.sap.post("/WebServices/ArtifactsWs.asmx/QueryAttachmentsDatablocked", {
            "EntityID": entity_id,
            "StartRow": start_row,
            "Max": max
        })

    def query_attachments_total(self, entity_id):
        """Get total attachment count for pagination."""
        return self.sap.post("/WebServices/ArtifactsWs.asmx/QueryAttachmentsDatablockedTotal", {
            "EntityID": entity_id
        })

    def get_mobile_artifacts(self, entity_id):
        """Get mobile artifacts (alternate endpoint)."""
        return self.sap.post("/WebServices/ArtifactsWs.asmx/GetMobileArtifacts", {
            "EntityID": entity_id
        })

    def get_mobile_artifacts_datablock(self, entity_id):
        """Get mobile artifacts in datablock format."""
        return self.sap.post("/WebServices/ArtifactsWs.asmx/GetMobileArtifactsDatablock", {
            "EntityID": entity_id
        })

    def get_form_response_artifacts(self, form_response_id):
        """Get artifacts attached to a form response."""
        return self.sap.post("/WebServices/ArtifactsWs.asmx/GetFormResponseArtifacts", {
            "FormResponseID": form_response_id
        })

    def check_for_mobile(self, entity_id):
        """Check if mobile artifacts exist for an entity (quick boolean check)."""
        return self.sap.post("/webservices/ArtifactsWs.asmx/CheckForMobileArtifacts", {
            "EntityID": entity_id
        })

    # ─── UPDATE / DELETE ─────────────────────────────────────────────────────

    def update(self, artifact_data):
        """Update artifact metadata (name, description, mobile visibility, etc.)"""
        return self.sap.post("/WebServices/ArtifactsWs.asmx/UpdateArtifact", artifact_data)

    def delete(self, artifact_guid):
        """Delete a single artifact by GUID."""
        return self.sap.post("/WebServices/ArtifactsWs.asmx/DeleteArtifact", {
            "ArtifactID": artifact_guid
        })

    def delete_multiple(self, artifact_guids):
        """Delete multiple artifacts by GUID list."""
        return self.sap.post("/WebServices/ArtifactsWs.asmx/DeleteArtifacts", {
            "ArtifactIDs": artifact_guids
        })

    # ─── STATS ───────────────────────────────────────────────────────────────

    def get_cdn_stats(self):
        """Get CDN file storage stats for the company."""
        return self.sap.post("/WebServices/ArtifactsWs.asmx/GetCDNFileStats", {})

    # ─── HELPERS ─────────────────────────────────────────────────────────────

    def get_photos(self, client_guid):
        """Shortcut: get all property photos for a client.
        Uses QueryMobile — the correct path for FileUpload-sourced photos.
        """
        return self.query_mobile(client_guid)
