import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import EbomDraft, HistoricalBom, Order, User
from app.seed import DATA_DIR, parse_csv
from app.services.batch_generator import generate_batch
from app.services.document_parser import parse_document
from app.services.ebom_generator import generate_draft
from app.main import find_duplicate_order


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(User(username="tester", password="demo", display_name="测试", role="admin"))
    source = DATA_DIR / "demo_seed_bom.csv"
    session.add_all(parse_csv(source.read_text(encoding="utf-8-sig"), source.name))
    session.commit()
    try:
        yield session
    finally:
        session.close()


def make_order(db, specification="7.0mm HB 六角杆", color_no="BLUE-02"):
    user = db.query(User).filter_by(username="tester").one()
    order = Order(
        order_no="TEST-001",
        product_family="HB六角铅笔",
        specification=specification,
        color_no=color_no,
        aux_materials_json=json.dumps(["银色烫印", "白色橡皮头", "12支盒彩盒"], ensure_ascii=False),
        quantity=12000,
        status="已确认字段",
        created_by=user.id,
    )
    db.add(order)
    db.flush()
    return user, order


def test_parse_docx_prefers_order_header_over_later_duplicate_text():
    sample = DATA_DIR / "demo_orders" / "客户订单_PO-2026-0917-001.docx"
    parsed = parse_document(sample.name, sample.read_bytes())
    assert parsed["order_no"] == "PO-2026-0917-001"
    assert parsed["product_family"] == "HB六角铅笔"
    assert parsed["quantity"] == 12000


def test_parse_sample_order():
    sample = DATA_DIR / "demo_orders" / "order_pencil_001.txt"
    parsed = parse_document(sample.name, sample.read_bytes())
    assert parsed["order_no"] == "PO-2026-0916-001"
    assert parsed["specification"] == "7.0mm HB 六角杆"
    assert parsed["color_no"] == "BLUE-02"
    assert parsed["quantity"] == 12000
    assert not parsed["missing_fields"]


def copy_bom_version(
    db,
    source_version,
    target_version,
    *,
    color_no=None,
    aux_materials=None,
    material_code_suffix="",
):
    source_lines = db.query(HistoricalBom).filter_by(bom_version=source_version).all()
    for source in source_lines:
        db.add(
            HistoricalBom(
                bom_code=source.bom_code,
                bom_version=target_version,
                source_name="测试历史BOM",
                source_order_no=f"HIST-{target_version}",
                product_family=source.product_family,
                applicable_specification=source.applicable_specification,
                applicable_color_no=color_no or source.applicable_color_no,
                applicable_aux_json=json.dumps(aux_materials, ensure_ascii=False)
                if aux_materials is not None
                else source.applicable_aux_json,
                line_no=source.line_no,
                level=source.level,
                parent_material_code=source.parent_material_code,
                material_category=source.material_category,
                material_code=source.material_code + material_code_suffix,
                material_name=source.material_name,
                quantity=source.quantity,
                unit=source.unit,
            )
        )
    db.flush()


def test_generate_known_variant(db):
    user, order = make_order(db)
    draft = generate_draft(db, order, user)
    assert draft.generation_status == "待复核"
    assert draft.source_bom_code == "BOM-HB-HEX"
    assert draft.source_bom_version == "V2"
    assert len(draft.lines) == 6
    quantities = {line.material_code: line.quantity for line in draft.lines}
    assert quantities["WOOD-HEX-70"] == 12000
    assert quantities["CORE-HB-20"] == 12000
    assert quantities["PAINT-BLUE-02"] == 360
    assert quantities["PRINT-SILVER"] == 12000
    assert quantities["ERASER-WHITE"] == 12000
    assert quantities["BOX-COLOR-12"] == 1008
    paint_original = json.loads(
        next(line for line in draft.lines if line.material_code == "PAINT-BLUE-02").ai_original_json
    )
    assert paint_original["unit_quantity"] == 0.03
    assert paint_original["order_quantity"] == 12000
    assert paint_original["quantity"] == 360
    assert json.loads(draft.validation_json)["blocking"] == []
    assert not any(line.requires_review for line in draft.lines)


def test_generate_prefers_highest_exact_matching_version(db):
    copy_bom_version(db, "V2", "V10", material_code_suffix="-V10")
    user, order = make_order(db)
    draft = generate_draft(db, order, user)
    assert draft.source_bom_version == "V10"
    assert all(line.source_bom_version == "V10" for line in draft.lines)
    assert any(line.material_code.endswith("-V10") for line in draft.lines)


def test_exact_fields_take_priority_over_higher_mismatched_version(db):
    copy_bom_version(
        db,
        "V2",
        "V99",
        color_no="BLACK-99",
        aux_materials=["未知辅料"],
        material_code_suffix="-V99",
    )
    user, order = make_order(db)
    draft = generate_draft(db, order, user)
    assert draft.source_bom_version == "V2"
    assert not any(line.material_code.endswith("-V99") for line in draft.lines)


def test_unknown_specification_fails_safely(db):
    user, order = make_order(db, specification="8.0mm 2B 圆杆", color_no="BLACK-01")
    draft = generate_draft(db, order, user)
    assert draft.generation_status == "生成失败"
    assert "未找到足够匹配的历史 BOM" in draft.failure_reason
    assert draft.lines == []


def test_find_duplicate_order_excludes_current_order(db):
    _, order = make_order(db)
    assert find_duplicate_order(db, " test-001 ").id == order.id
    assert find_duplicate_order(db, "TEST-001", exclude_order_id=order.id) is None
    assert find_duplicate_order(db, "   ") is None


def test_batch_derivation_does_not_multiply_quantities_twice(db):
    user, order = make_order(db)
    base = generate_draft(db, order, user)
    base.generation_status = "已确认"
    db.flush()
    job = generate_batch(
        db,
        base,
        [
            {
                "order_no": "TEST-BATCH-BLUE",
                "specification": order.specification,
                "color_no": order.color_no,
                "aux_materials": json.loads(order.aux_materials_json),
            }
        ],
        user,
    )
    assert job.items[0].status == "success"
    result = db.query(EbomDraft).filter_by(id=job.items[0].result_draft_id).one()
    quantities = {line.material_code: line.quantity for line in result.lines}
    assert quantities["WOOD-HEX-70"] == 12000
    assert quantities["PAINT-BLUE-02"] == 360
    assert quantities["BOX-COLOR-12"] == 1008


def test_batch_rejects_specification_change(db):
    user, order = make_order(db)
    base = generate_draft(db, order, user)
    base.generation_status = "已确认"
    db.flush()
    job = generate_batch(
        db,
        base,
        [
            {
                "order_no": "TEST-BATCH-001",
                "specification": "8.0mm 2B 圆杆",
                "color_no": "BLACK-01",
                "aux_materials": ["未知辅料"],
            }
        ],
        user,
    )
    assert job.status == "completed_with_issues"
    assert job.manual_review_count == 1
    assert job.items[0].status == "manual_review"
    assert "规格变化" in job.items[0].message
