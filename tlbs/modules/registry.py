from dataclasses import dataclass
@dataclass(frozen=True, slots=True)
class ModuleDefinition:
    key: str
    title: str
    description: str
    status: str
MODULES = (
 ModuleDefinition("media_capture","Media Capture","Capture and digitize video and audio media.","Separate application for now"),
 ModuleDefinition("receipt_manager","Receipt Manager","OCR, review, organize, and export receipts.","Existing module"),
 ModuleDefinition("relationship_manager","Relationship Manager","Scan business cards and manage follow-ups.","Planned"),
 ModuleDefinition("document_center","Document Center","OCR, organize, and search important documents.","Planned"),
 ModuleDefinition("client_vault","Client Vault","Securely deliver and archive customer files.","Planned"),
 ModuleDefinition("reports","Reports & Analytics","Track jobs, production, and business performance.","Planned"),
)
