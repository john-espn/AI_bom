import csv
import json
import math
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Base, SessionLocal, engine
from .models import HistoricalBom, User


DATA_DIR = Path(__file__).resolve().parent / "data"
REQUIRED_COLUMNS = {
    "bom_code",
    "bom_version",
    "source_name",
    "source_order_no",
    "product_family",
    "applicable_specification",
    "applicable_color_no",
    "applicable_aux",
    "line_no",
    "level",
    "parent_material_code",
    "material_category",
    "material_code",
    "material_name",
    "quantity",
    "unit",
}


def parse_csv(content: str, source_name: str) -> list[HistoricalBom]:
    reader = csv.DictReader(content.splitlines())
    if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(set(reader.fieldnames)):
        raise ValueError("历史 BOM 导入失败，请检查字段和文件内容")
    rows = []
    try:
        for record in reader:
            if any(not record.get(key, "").strip() for key in REQUIRED_COLUMNS - {"applicable_aux"}):
                raise ValueError("required field missing")
            quantity = float(record["quantity"])
            level = int(record["level"])
            line_no = int(record["line_no"])
            if not math.isfinite(quantity) or quantity <= 0 or level < 1 or line_no < 1:
                raise ValueError("invalid numeric value")
            rows.append(
                HistoricalBom(
                    bom_code=record["bom_code"].strip(),
                    bom_version=record["bom_version"].strip(),
                    source_name=source_name,
                    source_order_no=record["source_order_no"].strip(),
                    product_family=record["product_family"].strip(),
                    applicable_specification=record["applicable_specification"].strip(),
                    applicable_color_no=record["applicable_color_no"].strip(),
                    applicable_aux_json=json.dumps(
                        [value.strip() for value in record["applicable_aux"].split(";") if value.strip()],
                        ensure_ascii=False,
                    ),
                    line_no=line_no,
                    level=level,
                    parent_material_code=record["parent_material_code"].strip(),
                    material_category=record["material_category"].strip(),
                    material_code=record["material_code"].strip(),
                    material_name=record["material_name"].strip(),
                    quantity=quantity,
                    unit=record["unit"].strip(),
                )
            )
        if not rows:
            raise ValueError("no rows")
    except (TypeError, KeyError, ValueError) as exc:
        raise ValueError("历史 BOM 导入失败，请检查字段和文件内容") from exc
    return rows


def seed(db: Session) -> None:
    if not db.scalar(select(User.id).limit(1)):
        for username, name, role in (
            ("buyer", "采购演示账号", "buyer"),
            ("engineer", "工艺演示账号", "engineer"),
            ("admin", "管理员演示账号", "admin"),
        ):
            db.add(User(username=username, password="demo123", display_name=name, role=role))
    if not db.scalar(select(HistoricalBom.id).limit(1)):
        file = DATA_DIR / "demo_seed_bom.csv"
        db.add_all(parse_csv(file.read_text(encoding="utf-8-sig"), file.name))
    db.commit()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed(db)


if __name__ == "__main__":
    init_db()
    print("演示数据初始化完成")
