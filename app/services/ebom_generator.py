import json

from sqlalchemy.orm import Session

from ..models import EbomDraft, EbomLine, HistoricalBom, Order, User
from .bom_repository import find_candidates, find_exact_category_line
from .validator import validate_draft, validate_order


CHANGEABLE_CATEGORIES = {"color", "foil", "eraser", "package"}


def calculate_quantity(
    selected: HistoricalBom | EbomLine,
    order: Order,
    base_draft: EbomDraft | None,
) -> tuple[float, float]:
    if isinstance(selected, HistoricalBom):
        unit_quantity = selected.quantity
    else:
        base_order_quantity = base_draft.order.quantity if base_draft else 0
        unit_quantity = (
            selected.quantity / base_order_quantity
            if base_order_quantity > 0
            else selected.quantity
        )
    return round(unit_quantity * order.quantity, 6), unit_quantity


def generate_draft(db: Session, order: Order, user: User, base_draft: EbomDraft | None = None) -> EbomDraft:
    order_validation = validate_order(order)
    draft = EbomDraft(order_id=order.id, generated_by=user.id)
    db.add(draft)
    db.flush()
    if order_validation["blocking"]:
        draft.generation_status = "生成失败"
        draft.failure_reason = "；".join(order_validation["blocking"])
        draft.validation_json = json.dumps(order_validation, ensure_ascii=False)
        return draft

    candidates = find_candidates(db, order)
    exact_matches = [candidate for candidate in candidates if candidate.exact_applicability]
    if not exact_matches and base_draft is None:
        draft.generation_status = "生成失败"
        draft.failure_reason = "未找到足够匹配的历史 BOM，请人工复核"
        draft.validation_json = json.dumps(
            {"blocking": [draft.failure_reason], "warnings": []}, ensure_ascii=False
        )
        return draft

    base = base_draft if base_draft is not None else exact_matches[0]
    draft.source_bom_code = base.source_bom_code if base_draft else base.bom_code
    draft.source_bom_version = base.source_bom_version if base_draft else base.bom_version
    order_aux = json.loads(order.aux_materials_json or "[]")
    changes = []
    for source in base.lines:
        selected = source
        basis = "规格完全匹配，沿用历史 BOM 结构"
        difference = "无差异"
        confidence = source.confidence if base_draft else min(0.98, 0.68 + base.score / 300)
        requires_review = False
        if source.material_category in CHANGEABLE_CATEGORIES:
            replacement = find_exact_category_line(
                db,
                order.specification,
                order.color_no,
                source.material_category,
                order_aux,
                order.product_family,
            )
            if replacement:
                selected = replacement
                if source.material_code != selected.material_code:
                    basis = "按已审核历史 BOM 的色号/辅料映射替换"
                    difference = f"{source.material_name} → {selected.material_name}"
                    changes.append(difference)
                confidence = 0.94
            else:
                basis = "未找到明确历史依据，需人工复核"
                difference = f"目标色号/辅料没有 {source.material_category} 映射"
                confidence = 0.45
                requires_review = True
                changes.append(difference)
        generated_quantity, unit_quantity = calculate_quantity(selected, order, base_draft)
        original = {
            "material_code": selected.material_code,
            "material_name": selected.material_name,
            "unit_quantity": unit_quantity,
            "order_quantity": order.quantity,
            "quantity": generated_quantity,
            "unit": selected.unit,
            "difference_explanation": difference,
        }
        draft.lines.append(
            EbomLine(
                line_no=source.line_no,
                level=source.level,
                parent_material_code=source.parent_material_code,
                material_category=source.material_category,
                material_code=selected.material_code,
                material_name=selected.material_name,
                quantity=generated_quantity,
                unit=selected.unit,
                source_bom_code=(
                    selected.bom_code
                    if hasattr(selected, "bom_code")
                    else selected.source_bom_code
                ),
                source_bom_version=(
                    selected.bom_version
                    if hasattr(selected, "bom_version")
                    else selected.source_bom_version
                ),
                derivation_basis=basis,
                difference_explanation=difference,
                confidence=confidence,
                requires_review=requires_review,
                ai_original_json=json.dumps(original, ensure_ascii=False),
            )
        )
    db.flush()
    validation = validate_draft(draft)
    draft.validation_json = json.dumps(validation, ensure_ascii=False)
    draft.overall_confidence = round(
        sum(line.confidence for line in draft.lines) / len(draft.lines), 2
    )
    draft.difference_summary = "；".join(changes) if changes else "订单与历史 BOM 关键字段一致"
    draft.generation_status = "待复核"
    return draft
