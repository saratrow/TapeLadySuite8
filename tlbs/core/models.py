from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4


class ProjectType(StrEnum):
    RECEIPTS = "Receipt Processing"
    MEDIA = "Media Transfer"
    DOCUMENTS = "Document Scanning"
    RELATIONSHIPS = "Business Cards / Relationships"
    OTHER = "Other"


class ProjectStatus(StrEnum):
    NEW = "New"
    ACTIVE = "Active"
    WAITING = "Waiting"
    COMPLETE = "Complete"
    ARCHIVED = "Archived"


@dataclass(slots=True)
class Customer:
    name: str
    company: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    notes: str = ""
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass(slots=True)
class Project:
    customer_id: UUID
    name: str
    project_type: ProjectType = ProjectType.OTHER
    status: ProjectStatus = ProjectStatus.NEW
    description: str = ""
    due_date: datetime | None = None
    folder_path: str = ""
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass(slots=True)
class Activity:
    title: str
    details: str = ""
    customer_id: UUID | None = None
    project_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=datetime.now)


@dataclass(slots=True)
class TaskItem:
    title: str
    details: str = ""
    customer_id: UUID | None = None
    project_id: UUID | None = None
    due_date: datetime | None = None
    completed: bool = False
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass(slots=True)
class Asset:
    project_id: UUID
    file_name: str
    file_path: str
    asset_type: str = "Unknown"
    id: UUID = field(default_factory=uuid4)
    added_at: datetime = field(default_factory=datetime.now)


@dataclass(slots=True)
class Contact:
    customer_id: UUID
    name: str
    email: str = ""
    phone: str = ""
    title: str = ""
    notes: str = ""
    id: UUID = field(default_factory=uuid4)


@dataclass(slots=True)
class Invoice:
    project_id: UUID
    amount: Decimal = Decimal("0.00")
    status: str = "Draft"
    invoice_number: str = ""
    id: UUID = field(default_factory=uuid4)
    issued_at: datetime = field(default_factory=datetime.now)
    due_date: datetime | None = None
