import re
from io import BytesIO
from pathlib import Path

from docx import Document


FIELD_SEPARATOR = r"[ \t]*(?:[：:]|\|)[ \t]*"
FIELD_PATTERNS = {
    "order_no": rf"(?:订单编号|订单号){FIELD_SEPARATOR}([^\s|，,]+)",
    "product_family": rf"^(?:产品名称|产品){FIELD_SEPARATOR}([^|\r\n]+)",
    "specification": rf"规格{FIELD_SEPARATOR}([^|\r\n]+)",
    "color_no": rf"(?:色号|颜色编号){FIELD_SEPARATOR}([^\s|，,]+)",
    "aux_materials": rf"辅料{FIELD_SEPARATOR}([^|\r\n]+)",
    "quantity": rf"数量{FIELD_SEPARATOR}([\d,.]+)",
}
REQUIRED_FIELDS = ("order_no", "specification", "color_no", "aux_materials")
DETAIL_HEADERS = ("产品名称", "规格", "色号", "数量")


def extract_text(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".txt":
        for encoding in ("utf-8-sig", "gb18030"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("订单文档无法读取，请检查文件格式")
    elif suffix == ".docx":
        try:
            document = Document(BytesIO(content))
            blocks = []
            for block in document.iter_inner_content():
                if hasattr(block, "rows"):
                    blocks.extend(
                        " | ".join(cell.text.strip() for cell in row.cells)
                        for row in block.rows
                    )
                else:
                    blocks.append(block.text)
            text = "\n".join(blocks)
        except Exception as exc:
            raise ValueError("订单文档无法读取，请检查文件格式") from exc
    else:
        raise ValueError("订单文档无法读取，请检查文件格式")
    if not text.strip():
        raise ValueError("订单文档解析失败，请检查文档内容或联系管理员")
    return text


def parse_detail_row(text: str) -> dict:
    """Read the first order-detail row, where labels and values are separate cells."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        cells = [cell.strip() for cell in line.split("|")]
        if not all(header in cells for header in DETAIL_HEADERS):
            continue
        positions = {header: cells.index(header) for header in DETAIL_HEADERS}
        aux_header = next((header for header in ("定制辅料", "辅料") if header in cells), None)
        if index + 1 >= len(lines):
            break
        row = [cell.strip() for cell in lines[index + 1].split("|")]
        if len(row) <= max(positions.values()):
            break
        return {
            "product_family": row[positions["产品名称"]],
            "specification": row[positions["规格"]],
            "color_no": row[positions["色号"]],
            "aux_materials": row[cells.index(aux_header)] if aux_header else "",
            "quantity": row[positions["数量"]],
            "snippet": line + "\\n" + lines[index + 1],
        }
    return {}


def parse_order_text(text: str) -> dict:
    values = {}
    snippets = {}
    confidences = {}
    for field, pattern in FIELD_PATTERNS.items():
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        value = match.group(1).strip() if match else ""
        values[field] = value
        snippets[field] = match.group(0).strip() if match else ""
        confidences[field] = 0.96 if value else 0.0

    detail = parse_detail_row(text)
    for field in ("product_family", "specification", "color_no", "aux_materials", "quantity"):
        if detail.get(field):
            values[field] = detail[field]
            snippets[field] = detail["snippet"]
            confidences[field] = 0.96

    aux_value = values["aux_materials"]
    aux_materials = [part.strip() for part in re.split(r"[、,，;；]", aux_value) if part.strip()]
    quantity_text = re.sub(r"[^\d,.]", "", values["quantity"])
    try:
        quantity = float(quantity_text.replace(",", "")) if quantity_text else 0
    except ValueError:
        quantity = 0
        confidences["quantity"] = 0.3
    product_family = values["product_family"] or "HB六角铅笔"
    if not values["product_family"]:
        confidences["product_family"] = 0.7

    missing = [field for field in REQUIRED_FIELDS if not values[field]]
    uncertain = [field for field, confidence in confidences.items() if 0 < confidence < 0.8]
    required_scores = [confidences[field] for field in REQUIRED_FIELDS]
    overall = round(sum(required_scores) / len(required_scores), 2)
    return {
        "order_no": values["order_no"],
        "product_family": product_family,
        "specification": values["specification"],
        "color_no": values["color_no"],
        "aux_materials": aux_materials,
        "quantity": quantity,
        "confidence": overall,
        "field_confidences": confidences,
        "missing_fields": missing,
        "uncertain_fields": uncertain,
        "source_snippets": snippets,
        "raw_text": text,
    }


def parse_document(filename: str, content: bytes) -> dict:
    return parse_order_text(extract_text(filename, content))
