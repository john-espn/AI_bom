from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> datetime:
    return datetime.now()


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password: Mapped[str] = mapped_column(String(128))
    display_name: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(32), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class UploadedDocument(Base):
    __tablename__ = "uploaded_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(128))
    storage_path: Mapped[str] = mapped_column(String(500))
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    parse_status: Mapped[str] = mapped_column(String(32), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_documents.id"))
    order_no: Mapped[str] = mapped_column(String(128), index=True)
    product_family: Mapped[str] = mapped_column(String(128), default="HB六角铅笔")
    specification: Mapped[str] = mapped_column(String(255), index=True)
    color_no: Mapped[str] = mapped_column(String(64), index=True)
    aux_materials_json: Mapped[str] = mapped_column(Text, default="[]")
    quantity: Mapped[float] = mapped_column(Float, default=0)
    parse_confidence: Mapped[float] = mapped_column(Float, default=0)
    field_confidences_json: Mapped[str] = mapped_column(Text, default="{}")
    missing_fields_json: Mapped[str] = mapped_column(Text, default="[]")
    uncertain_fields_json: Mapped[str] = mapped_column(Text, default="[]")
    source_snippets_json: Mapped[str] = mapped_column(Text, default="{}")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="待确认", index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class HistoricalBom(Base):
    __tablename__ = "historical_boms"
    id: Mapped[int] = mapped_column(primary_key=True)
    bom_code: Mapped[str] = mapped_column(String(128), index=True)
    bom_version: Mapped[str] = mapped_column(String(32))
    source_name: Mapped[str] = mapped_column(String(255))
    source_order_no: Mapped[str] = mapped_column(String(128))
    product_family: Mapped[str] = mapped_column(String(128), index=True)
    applicable_specification: Mapped[str] = mapped_column(String(255), index=True)
    applicable_color_no: Mapped[str] = mapped_column(String(64), index=True)
    applicable_aux_json: Mapped[str] = mapped_column(Text, default="[]")
    line_no: Mapped[int] = mapped_column(Integer)
    level: Mapped[int] = mapped_column(Integer, default=1)
    parent_material_code: Mapped[str] = mapped_column(String(128))
    material_category: Mapped[str] = mapped_column(String(64), default="base")
    material_code: Mapped[str] = mapped_column(String(128), index=True)
    material_name: Mapped[str] = mapped_column(String(255), index=True)
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class EbomDraft(Base):
    __tablename__ = "ebom_drafts"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    source_bom_code: Mapped[str | None] = mapped_column(String(128))
    source_bom_version: Mapped[str | None] = mapped_column(String(32))
    generation_status: Mapped[str] = mapped_column(String(32), default="待复核", index=True)
    overall_confidence: Mapped[float] = mapped_column(Float, default=0)
    difference_summary: Mapped[str] = mapped_column(Text, default="")
    validation_json: Mapped[str] = mapped_column(Text, default='{"blocking": [], "warnings": []}')
    failure_reason: Mapped[str | None] = mapped_column(Text)
    generated_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    version: Mapped[int] = mapped_column(Integer, default=1)
    order: Mapped[Order] = relationship()
    lines: Mapped[list["EbomLine"]] = relationship(cascade="all, delete-orphan", order_by="EbomLine.line_no")


class EbomLine(Base):
    __tablename__ = "ebom_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("ebom_drafts.id"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    level: Mapped[int] = mapped_column(Integer, default=1)
    parent_material_code: Mapped[str] = mapped_column(String(128))
    material_category: Mapped[str] = mapped_column(String(64), default="base")
    material_code: Mapped[str] = mapped_column(String(128))
    material_name: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(32))
    source_bom_code: Mapped[str] = mapped_column(String(128))
    source_bom_version: Mapped[str] = mapped_column(String(32))
    derivation_basis: Mapped[str] = mapped_column(Text)
    difference_explanation: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_original_json: Mapped[str] = mapped_column(Text, default="{}")
    human_correction_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class BatchJob(Base):
    __tablename__ = "batch_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    base_draft_id: Mapped[int] = mapped_column(ForeignKey("ebom_drafts.id"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(32), default="running")
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    manual_review_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    items: Mapped[list["BatchItem"]] = relationship(cascade="all, delete-orphan")


class BatchItem(Base):
    __tablename__ = "batch_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_job_id: Mapped[int] = mapped_column(ForeignKey("batch_jobs.id"), index=True)
    variant_order_no: Mapped[str] = mapped_column(String(128))
    specification: Mapped[str] = mapped_column(String(255))
    color_no: Mapped[str] = mapped_column(String(64))
    aux_materials_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32))
    result_draft_id: Mapped[int | None] = mapped_column(ForeignKey("ebom_drafts.id"))
    message: Mapped[str] = mapped_column(Text, default="")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    actor_role: Mapped[str] = mapped_column(String(32), default="anonymous")
    action: Mapped[str] = mapped_column(String(64), index=True)
    object_type: Mapped[str] = mapped_column(String(64))
    object_id: Mapped[str] = mapped_column(String(128))
    before_json: Mapped[str] = mapped_column(Text, default="{}")
    after_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    ip_address: Mapped[str | None] = mapped_column(String(64))
