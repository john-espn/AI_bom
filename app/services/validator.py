import json
import math

from ..models import EbomDraft


CONFIRMATION_THRESHOLD = 0.65


def validate_order(order) -> dict:
    blocking = []
    if not order.order_no.strip():
        blocking.append("缺少订单编号")
    if not order.specification.strip():
        blocking.append("缺少产品规格")
    if not order.color_no.strip():
        blocking.append("缺少色号")
    if not json.loads(order.aux_materials_json or "[]"):
        blocking.append("缺少辅料")
    if not math.isfinite(order.quantity) or order.quantity <= 0:
        blocking.append("订单数量必须为大于 0 的有限数值")
    return {"blocking": blocking, "warnings": []}


def validate_draft(draft: EbomDraft) -> dict:
    blocking = []
    warnings = []
    if not draft.lines:
        blocking.append("未生成 BOM 明细")
    seen = set()
    for line in draft.lines:
        if not line.material_code or not line.material_name or not line.unit:
            blocking.append(f"第 {line.line_no} 行缺少必填物料字段")
        if not math.isfinite(line.quantity) or line.quantity <= 0:
            blocking.append(f"第 {line.line_no} 行数量必须为大于 0 的有限数值")
        key = (line.line_no, line.material_code)
        if key in seen:
            blocking.append(f"第 {line.line_no} 行存在重复物料")
        seen.add(key)
        if line.requires_review or line.confidence < CONFIRMATION_THRESHOLD:
            blocking.append(f"第 {line.line_no} 行证据不足，需要人工补充")
        elif line.confidence < 0.8:
            warnings.append(f"第 {line.line_no} 行置信度偏低")
    return {"blocking": list(dict.fromkeys(blocking)), "warnings": list(dict.fromkeys(warnings))}
