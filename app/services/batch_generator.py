import json
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import BatchItem, BatchJob, EbomDraft, Order, User
from .ebom_generator import generate_draft
from .validator import validate_draft


def generate_batch(
    db: Session,
    base_draft: EbomDraft,
    variants: list[dict],
    user: User,
) -> BatchJob:
    job = BatchJob(base_draft_id=base_draft.id, created_by=user.id)
    db.add(job)
    db.flush()
    base_order = base_draft.order
    for variant in variants:
        order_no = variant.get("order_no", "").strip()
        specification = variant.get("specification", "").strip()
        color_no = variant.get("color_no", "").strip()
        aux = variant.get("aux_materials", [])
        item = BatchItem(
            variant_order_no=order_no,
            specification=specification,
            color_no=color_no,
            aux_materials_json=json.dumps(aux, ensure_ascii=False),
            status="failed",
        )
        job.items.append(item)
        if not order_no or not specification or not color_no:
            item.message = "订单编号、规格和色号为必填项"
            job.failed_count += 1
            continue
        order = Order(
            order_no=order_no,
            product_family=base_order.product_family,
            specification=specification,
            color_no=color_no,
            aux_materials_json=json.dumps(aux, ensure_ascii=False),
            quantity=base_order.quantity,
            parse_confidence=1,
            field_confidences_json="{}",
            status="已确认字段",
            created_by=user.id,
        )
        db.add(order)
        db.flush()
        if specification != base_order.specification:
            order.status = "待确认"
            item.status = "manual_review"
            item.message = "规格变化超出批量派生边界，请人工复核"
            job.manual_review_count += 1
            continue
        draft = generate_draft(db, order, user, base_draft=base_draft)
        db.flush()
        item.result_draft_id = draft.id
        if draft.generation_status == "生成失败":
            item.status = "manual_review"
            item.message = draft.failure_reason or "历史依据不足"
            job.manual_review_count += 1
        elif validate_draft(draft)["blocking"]:
            item.status = "manual_review"
            item.message = "生成结果存在校验问题，需人工复核"
            job.manual_review_count += 1
        else:
            item.status = "success"
            item.message = "EBOM 草稿生成成功"
            job.success_count += 1
    job.status = "completed" if not (job.failed_count or job.manual_review_count) else "completed_with_issues"
    job.completed_at = datetime.now()
    return job
