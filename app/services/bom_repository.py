import json
import re
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import HistoricalBom, Order


@dataclass
class BomCandidate:
    bom_code: str
    bom_version: str
    score: int
    reason: str
    lines: list[HistoricalBom]
    exact_applicability: bool = False


def aux_material_set(raw_value: str | None) -> set[str]:
    try:
        values = json.loads(raw_value or "[]")
    except (TypeError, json.JSONDecodeError):
        return set()
    return {str(value).strip() for value in values if str(value).strip()}


def version_sort_key(version: str) -> tuple[tuple[int, int | str], ...]:
    parts = re.findall(r"\d+|[^\d]+", (version or "").strip().casefold())
    return tuple((1, int(part)) if part.isdigit() else (0, part) for part in parts)


def candidate_matches_order(candidate: BomCandidate, order: Order) -> bool:
    sample = candidate.lines[0]
    return (
        sample.product_family == order.product_family
        and sample.applicable_specification == order.specification
        and sample.applicable_color_no == order.color_no
        and aux_material_set(sample.applicable_aux_json)
        == aux_material_set(order.aux_materials_json)
    )


def find_candidates(db: Session, order: Order) -> list[BomCandidate]:
    rows = db.scalars(select(HistoricalBom)).all()
    groups: dict[tuple[str, str], list[HistoricalBom]] = defaultdict(list)
    for row in rows:
        groups[(row.bom_code, row.bom_version)].append(row)

    order_aux = aux_material_set(order.aux_materials_json)
    candidates = []
    for (bom_code, version), lines in groups.items():
        sample = lines[0]
        sample_aux = aux_material_set(sample.applicable_aux_json)
        score = 0
        reasons = []
        if sample.applicable_specification == order.specification:
            score += 50
            reasons.append("规格完全匹配")
        elif (
            order.specification in sample.applicable_specification
            or sample.applicable_specification in order.specification
        ):
            score += 25
            reasons.append("规格近似匹配")
        if sample.product_family == order.product_family:
            score += 20
            reasons.append("产品系列匹配")
        if sample.applicable_color_no == order.color_no:
            score += 20
            reasons.append("色号匹配")
        if sample_aux == order_aux:
            score += 10
            reasons.append("辅料完全匹配")
        elif order_aux and sample_aux:
            overlap = order_aux & sample_aux
            score += min(9, round(9 * len(overlap) / len(order_aux)))
            if overlap:
                reasons.append("辅料存在匹配")
        exact_applicability = (
            sample.product_family == order.product_family
            and sample.applicable_specification == order.specification
            and sample.applicable_color_no == order.color_no
            and sample_aux == order_aux
        )
        if score > 0:
            candidates.append(
                BomCandidate(
                    bom_code=bom_code,
                    bom_version=version,
                    score=score,
                    reason="、".join(reasons),
                    lines=sorted(lines, key=lambda line: line.line_no),
                    exact_applicability=exact_applicability,
                )
            )
    return sorted(
        candidates,
        key=lambda item: (
            item.exact_applicability,
            item.score,
            version_sort_key(item.bom_version),
            item.bom_code,
        ),
        reverse=True,
    )


def find_exact_category_line(
    db: Session,
    specification: str,
    color_no: str,
    category: str,
    aux_materials: list[str],
    product_family: str,
) -> HistoricalBom | None:
    rows = db.scalars(
        select(HistoricalBom).where(
            HistoricalBom.applicable_specification == specification,
            HistoricalBom.product_family == product_family,
            HistoricalBom.material_category == category,
        )
    ).all()
    order_aux = {value.strip() for value in aux_materials if value.strip()}
    matches = []
    for row in rows:
        category_match = False
        if category == "color":
            category_match = row.applicable_color_no == color_no
        elif row.material_name in order_aux:
            category_match = True
        elif category == "foil" and any(value in row.material_name for value in order_aux):
            category_match = True
        if category_match:
            applicability_match = (
                row.applicable_color_no == color_no
                and aux_material_set(row.applicable_aux_json) == order_aux
            )
            matches.append((applicability_match, row))
    if not matches:
        return None
    return max(
        matches,
        key=lambda item: (
            item[0],
            version_sort_key(item[1].bom_version),
            item[1].bom_code,
            -item[1].line_no,
        ),
    )[1]
