import json
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload
from starlette.middleware.sessions import SessionMiddleware

from .auth import ROLE_LABELS, authenticate, current_user, require_role, require_user
from .db import BASE_DIR, get_db
from .models import AuditLog, BatchJob, EbomDraft, EbomLine, HistoricalBom, Order, UploadedDocument, User
from .permissions import can
from .seed import init_db, parse_csv
from .services.audit import log_action
from .services.batch_generator import generate_batch
from .services.bom_repository import find_candidates
from .services.document_parser import parse_document
from .services.ebom_generator import generate_draft
from .services.validator import validate_draft, validate_order


UPLOAD_DIR = BASE_DIR / "uploads"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    UPLOAD_DIR.mkdir(exist_ok=True)
    init_db()
    yield


app = FastAPI(title="铅笔制造 AI-BOM 智能体", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "ai-bom-demo-change-me"),
    same_site="lax",
    https_only=False,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def set_flash(request: Request, message: str, kind: str = "success") -> None:
    request.session["flash"] = {"message": message, "kind": kind}


def redirect(path: str, status_code: int = status.HTTP_303_SEE_OTHER) -> RedirectResponse:
    return RedirectResponse(path, status_code=status_code)


def render(request: Request, db: Session, template: str, **context) -> HTMLResponse:
    user = current_user(request, db)
    values = {
        "request": request,
        "user": user,
        "role_labels": ROLE_LABELS,
        "can": can,
        "flash": request.session.pop("flash", None),
    }
    values.update(context)
    return templates.TemplateResponse(request=request, name=template, context=values)


def logged_in(request: Request, db: Session) -> User | RedirectResponse:
    user = current_user(request, db)
    return user if user else redirect("/login", status.HTTP_303_SEE_OTHER)


def require_permission(user: User, permission: str) -> None:
    if not can(user.role, permission):
        raise HTTPException(status_code=403, detail="当前账号无权执行此操作")


def load_draft(db: Session, draft_id: int) -> EbomDraft:
    draft = db.scalar(
        select(EbomDraft)
        .options(selectinload(EbomDraft.lines), selectinload(EbomDraft.order))
        .where(EbomDraft.id == draft_id)
    )
    if not draft:
        raise HTTPException(status_code=404, detail="未找到 BOM 草稿")
    return draft


def json_value(value: str, fallback):
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return fallback


def find_duplicate_order(
    db: Session,
    order_no: str,
    exclude_order_id: int | None = None,
) -> Order | None:
    normalized = order_no.strip()
    if not normalized:
        return None
    statement = select(Order).where(func.lower(Order.order_no) == normalized.lower())
    if exclude_order_id is not None:
        statement = statement.where(Order.id != exclude_order_id)
    return db.scalar(statement.limit(1))


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        return redirect("/login")
    with next(get_db()) as db:
        return render(
            request,
            db,
            "error.html",
            status_code=exc.status_code,
            message=str(exc.detail),
        )


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    if current_user(request, db):
        return redirect("/")
    return render(request, db, "login.html")


@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = authenticate(db, username.strip(), password)
    if not user:
        log_action(db, None, "login_failed", "session", username, ip_address=client_ip(request))
        db.commit()
        return render(request, db, "login.html", error="用户名或密码错误")
    request.session.clear()
    request.session["user_id"] = user.id
    log_action(db, user, "login", "session", user.id, ip_address=client_ip(request))
    db.commit()
    return redirect("/")


@app.get("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if user:
        log_action(db, user, "logout", "session", user.id, ip_address=client_ip(request))
        db.commit()
    request.session.clear()
    return redirect("/login")


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = logged_in(request, db)
    if isinstance(user, RedirectResponse):
        return user
    draft_counts = dict(
        db.execute(select(EbomDraft.generation_status, func.count()).group_by(EbomDraft.generation_status)).all()
    )
    recent_drafts = db.scalars(
        select(EbomDraft)
        .options(selectinload(EbomDraft.order))
        .order_by(EbomDraft.generated_at.desc())
        .limit(8)
    ).all()
    recent_batches = db.scalars(select(BatchJob).order_by(BatchJob.created_at.desc()).limit(5)).all()
    return render(
        request,
        db,
        "dashboard.html",
        draft_counts=draft_counts,
        recent_drafts=recent_drafts,
        recent_batches=recent_batches,
        order_count=db.scalar(select(func.count(Order.id))) or 0,
        knowledge_count=db.scalar(select(func.count(HistoricalBom.id))) or 0,
    )


@app.get("/orders/upload", response_class=HTMLResponse)
def upload_page(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    require_permission(user, "upload")
    return render(request, db, "order_upload.html")


@app.post("/orders/upload")
async def upload_order(
    request: Request,
    document: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    require_permission(user, "upload")
    filename = Path(document.filename or "order.txt").name
    content = await document.read()
    if not content or len(content) > 5 * 1024 * 1024:
        return render(request, db, "order_upload.html", error="订单文档无法读取，请检查文件格式")
    stored_name = f"{datetime.now():%Y%m%d%H%M%S%f}_{filename}"
    storage_path = UPLOAD_DIR / stored_name
    storage_path.write_bytes(content)
    uploaded = UploadedDocument(
        filename=filename,
        content_type=document.content_type,
        storage_path=str(storage_path),
        uploaded_by=user.id,
    )
    db.add(uploaded)
    db.flush()
    try:
        parsed = parse_document(filename, content)
    except ValueError as exc:
        uploaded.parse_status = "failed"
        uploaded.error_message = str(exc)
        log_action(db, user, "upload_failed", "document", uploaded.id, after={"error": str(exc)})
        db.commit()
        return render(request, db, "order_upload.html", error=str(exc))
    duplicate = find_duplicate_order(db, parsed["order_no"])
    if duplicate and duplicate.status != "待确认":
        message = f"订单号 {parsed['order_no']} 已存在，请修改订单文档中的订单号后重新上传"
        uploaded.parse_status = "failed"
        uploaded.error_message = message
        log_action(
            db,
            user,
            "upload_duplicate_order",
            "document",
            uploaded.id,
            after={"order_no": parsed["order_no"], "duplicate_order_id": duplicate.id},
        )
        db.commit()
        return render(
            request,
            db,
            "order_upload.html",
            error=message,
            parsed_order_no=parsed["order_no"],
        )
    uploaded.parse_status = "parsed"
    if duplicate:
        # A failed/incomplete parse has no draft yet; replace it on re-upload
        # instead of leaving an orphan order that blocks the corrected document.
        order = duplicate
        before = {
            "order_no": order.order_no,
            "status": order.status,
            "document_id": order.document_id,
        }
        order.document_id = uploaded.id
    else:
        order = Order(
            document_id=uploaded.id,
            order_no=parsed["order_no"],
            created_by=user.id,
        )
        db.add(order)
        before = {}
    order.order_no = parsed["order_no"]
    order.product_family = parsed["product_family"]
    order.specification = parsed["specification"]
    order.color_no = parsed["color_no"]
    order.aux_materials_json = json.dumps(parsed["aux_materials"], ensure_ascii=False)
    order.quantity = parsed["quantity"]
    order.parse_confidence = parsed["confidence"]
    order.field_confidences_json = json.dumps(parsed["field_confidences"], ensure_ascii=False)
    order.missing_fields_json = json.dumps(parsed["missing_fields"], ensure_ascii=False)
    order.uncertain_fields_json = json.dumps(parsed["uncertain_fields"], ensure_ascii=False)
    order.source_snippets_json = json.dumps(parsed["source_snippets"], ensure_ascii=False)
    order.raw_text = parsed["raw_text"]
    order.status = "待确认"
    db.flush()
    log_action(db, user, "upload_parse", "order", order.id, after={"filename": filename, "confidence": parsed["confidence"]})
    db.commit()
    set_flash(request, "订单解析完成，请确认识别字段")
    return redirect(f"/orders/{order.id}/confirm")


@app.get("/orders/{order_id}/confirm", response_class=HTMLResponse)
def order_confirm_page(request: Request, order_id: int, db: Session = Depends(get_db)):
    user = require_user(request, db)
    require_permission(user, "generate")
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="未找到订单")
    candidates = find_candidates(db, order)
    return render(
        request,
        db,
        "order_confirm.html",
        order=order,
        aux_materials="、".join(json_value(order.aux_materials_json, [])),
        field_confidences=json_value(order.field_confidences_json, {}),
        missing_fields=json_value(order.missing_fields_json, []),
        source_snippets=json_value(order.source_snippets_json, {}),
        candidates=candidates[:5],
    )


@app.post("/orders/{order_id}/confirm")
def confirm_order_fields(
    request: Request,
    order_id: int,
    order_no: str = Form(""),
    product_family: str = Form(""),
    specification: str = Form(""),
    color_no: str = Form(""),
    aux_materials: str = Form(""),
    quantity: float = Form(0),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    require_permission(user, "generate")
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="未找到订单")
    before = {
        "order_no": order.order_no,
        "product_family": order.product_family,
        "specification": order.specification,
        "color_no": order.color_no,
        "aux_materials": json_value(order.aux_materials_json, []),
        "quantity": order.quantity,
    }
    aux = [part.strip() for part in re.split(r"[、,，;；]", aux_materials) if part.strip()]
    order.order_no = order_no.strip()
    order.product_family = product_family.strip() or "HB六角铅笔"
    order.specification = specification.strip()
    order.color_no = color_no.strip()
    order.aux_materials_json = json.dumps(aux, ensure_ascii=False)
    order.quantity = quantity
    validation = validate_order(order)
    duplicate = find_duplicate_order(db, order.order_no, exclude_order_id=order.id)
    if duplicate:
        validation["blocking"].append(
            f"订单号 {order.order_no} 已存在，请修改为新的订单号"
        )
    order.missing_fields_json = json.dumps(validation["blocking"], ensure_ascii=False)
    order.status = "已确认字段" if not validation["blocking"] else "待确认"
    after = {
        "order_no": order.order_no,
        "product_family": order.product_family,
        "specification": order.specification,
        "color_no": order.color_no,
        "aux_materials": aux,
        "quantity": order.quantity,
        "validation": validation,
    }
    log_action(db, user, "confirm_order_fields", "order", order.id, before, after)
    db.commit()
    if validation["blocking"]:
        set_flash(request, "字段仍不完整：" + "；".join(validation["blocking"]), "error")
    else:
        set_flash(request, "订单字段已确认，可以生成 EBOM 草稿")
    return redirect(f"/orders/{order.id}/confirm")


@app.post("/orders/{order_id}/generate")
def create_draft(request: Request, order_id: int, db: Session = Depends(get_db)):
    user = require_user(request, db)
    require_permission(user, "generate")
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="未找到订单")
    if order.status != "已确认字段":
        set_flash(request, "请先确认完整订单字段", "error")
        return redirect(f"/orders/{order.id}/confirm")
    draft = generate_draft(db, order, user)
    db.flush()
    log_action(
        db,
        user,
        "generate_ebom",
        "draft",
        draft.id,
        after={"status": draft.generation_status, "source_bom": draft.source_bom_code},
    )
    db.commit()
    set_flash(request, "EBOM 草稿生成完成" if draft.generation_status != "生成失败" else draft.failure_reason, "success" if draft.generation_status != "生成失败" else "error")
    return redirect(f"/drafts/{draft.id}")


@app.get("/drafts/{draft_id}", response_class=HTMLResponse)
def draft_detail(request: Request, draft_id: int, db: Session = Depends(get_db)):
    user = require_user(request, db)
    require_permission(user, "view")
    draft = load_draft(db, draft_id)
    return render(
        request,
        db,
        "draft_detail.html",
        draft=draft,
        validation=json_value(draft.validation_json, {"blocking": [], "warnings": []}),
    )


@app.post("/drafts/{draft_id}/edit")
async def edit_draft(request: Request, draft_id: int, db: Session = Depends(get_db)):
    user = require_user(request, db)
    require_permission(user, "edit")
    draft = load_draft(db, draft_id)
    if draft.generation_status == "已确认":
        raise HTTPException(status_code=409, detail="已确认 BOM 不允许直接修改")
    form = await request.form()
    changes = []
    for line in draft.lines:
        before = {
            "material_code": line.material_code,
            "material_name": line.material_name,
            "quantity": line.quantity,
            "unit": line.unit,
            "difference_explanation": line.difference_explanation,
        }
        try:
            quantity = float(str(form.get(f"quantity_{line.id}", line.quantity)))
        except ValueError:
            quantity = 0
        line.material_code = str(form.get(f"material_code_{line.id}", "")).strip()
        line.material_name = str(form.get(f"material_name_{line.id}", "")).strip()
        line.quantity = quantity
        line.unit = str(form.get(f"unit_{line.id}", "")).strip()
        line.difference_explanation = str(form.get(f"difference_explanation_{line.id}", "")).strip()
        after = {
            "material_code": line.material_code,
            "material_name": line.material_name,
            "quantity": line.quantity,
            "unit": line.unit,
            "difference_explanation": line.difference_explanation,
        }
        if before != after:
            line.human_correction_json = json.dumps({"before": before, "after": after}, ensure_ascii=False)
            line.updated_by = user.id
            material_resolved = (
                before["material_code"] != after["material_code"]
                or before["material_name"] != after["material_name"]
            )
            if material_resolved:
                line.requires_review = False
                line.confidence = max(line.confidence, 0.9)
            changes.append({"line_id": line.id, "before": before, "after": after})
    db.flush()
    validation = validate_draft(draft)
    draft.validation_json = json.dumps(validation, ensure_ascii=False)
    draft.overall_confidence = round(sum(line.confidence for line in draft.lines) / len(draft.lines), 2) if draft.lines else 0
    if changes:
        draft.generation_status = "已修正"
        draft.version += 1
    log_action(db, user, "edit_ebom", "draft", draft.id, before={}, after={"changes": changes, "validation": validation})
    db.commit()
    set_flash(request, "BOM 修改已保存" if changes else "未检测到 BOM 字段变化")
    return redirect(f"/drafts/{draft.id}")


@app.post("/drafts/{draft_id}/confirm")
def confirm_draft(request: Request, draft_id: int, db: Session = Depends(get_db)):
    user = require_user(request, db)
    require_role(user, "engineer", "admin")
    draft = load_draft(db, draft_id)
    validation = validate_draft(draft)
    draft.validation_json = json.dumps(validation, ensure_ascii=False)
    if validation["blocking"] or draft.generation_status == "生成失败":
        db.commit()
        set_flash(request, "BOM 存在阻断问题，无法确认：" + "；".join(validation["blocking"]), "error")
        return redirect(f"/drafts/{draft.id}")
    before = {"status": draft.generation_status}
    draft.generation_status = "已确认"
    draft.confirmed_by = user.id
    draft.confirmed_at = datetime.now()
    log_action(db, user, "confirm_ebom", "draft", draft.id, before, {"status": "已确认"})
    db.commit()
    set_flash(request, "EBOM 已由技术人员确认")
    return redirect(f"/drafts/{draft.id}")


@app.get("/batch", response_class=HTMLResponse)
def batch_page(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    require_permission(user, "batch")
    drafts = db.scalars(
        select(EbomDraft)
        .options(selectinload(EbomDraft.order))
        .where(EbomDraft.generation_status == "已确认")
        .order_by(EbomDraft.confirmed_at.desc())
    ).all()
    jobs = db.scalars(select(BatchJob).order_by(BatchJob.created_at.desc()).limit(10)).all()
    return render(request, db, "batch.html", drafts=drafts, jobs=jobs)


@app.post("/batch")
def create_batch(
    request: Request,
    base_draft_id: int = Form(...),
    variants: str = Form(""),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    require_permission(user, "batch")
    base_draft = load_draft(db, base_draft_id)
    if base_draft.generation_status != "已确认":
        raise HTTPException(status_code=409, detail="批量派生只能使用已确认 BOM")
    parsed_variants = []
    for raw_line in variants.splitlines():
        if not raw_line.strip():
            continue
        parts = [part.strip() for part in re.split(r"[,，]", raw_line, maxsplit=3)]
        parsed_variants.append(
            {
                "order_no": parts[0] if len(parts) > 0 else "",
                "specification": parts[1] if len(parts) > 1 else "",
                "color_no": parts[2] if len(parts) > 2 else "",
                "aux_materials": [item.strip() for item in re.split(r"[;；、]", parts[3]) if item.strip()] if len(parts) > 3 else [],
            }
        )
    if not parsed_variants:
        set_flash(request, "请至少输入一个批量变体", "error")
        return redirect("/batch")
    job = generate_batch(db, base_draft, parsed_variants, user)
    db.flush()
    log_action(
        db,
        user,
        "generate_batch",
        "batch_job",
        job.id,
        after={"success": job.success_count, "failed": job.failed_count, "manual_review": job.manual_review_count},
    )
    db.commit()
    set_flash(request, "批量 BOM 生成完成" if job.status == "completed" else "批量任务已完成，存在失败或待复核订单", "success" if job.status == "completed" else "warning")
    return redirect(f"/batch/{job.id}")


@app.get("/batch/{job_id}", response_class=HTMLResponse)
def batch_detail(request: Request, job_id: int, db: Session = Depends(get_db)):
    user = require_user(request, db)
    require_permission(user, "view")
    job = db.scalar(select(BatchJob).options(selectinload(BatchJob.items)).where(BatchJob.id == job_id))
    if not job:
        raise HTTPException(status_code=404, detail="未找到批量任务")
    return render(request, db, "batch_detail.html", job=job)


@app.get("/records", response_class=HTMLResponse)
def records(
    request: Request,
    order_no: str = "",
    color_no: str = "",
    record_status: str = "",
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    require_permission(user, "view")
    stmt = select(EbomDraft).join(EbomDraft.order).options(selectinload(EbomDraft.order))
    if order_no:
        stmt = stmt.where(Order.order_no.contains(order_no.strip()))
    if color_no:
        stmt = stmt.where(Order.color_no.contains(color_no.strip()))
    if record_status:
        stmt = stmt.where(EbomDraft.generation_status == record_status)
    drafts = db.scalars(stmt.order_by(EbomDraft.generated_at.desc()).limit(100)).all()
    return render(
        request,
        db,
        "records.html",
        drafts=drafts,
        filters={"order_no": order_no, "color_no": color_no, "record_status": record_status},
    )


@app.get("/knowledge", response_class=HTMLResponse)
def knowledge(
    request: Request,
    query: str = "",
    specification: str = "",
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    require_permission(user, "knowledge_view")
    stmt = select(HistoricalBom)
    if query:
        value = f"%{query.strip()}%"
        stmt = stmt.where(or_(HistoricalBom.bom_code.like(value), HistoricalBom.material_code.like(value), HistoricalBom.material_name.like(value)))
    if specification:
        stmt = stmt.where(HistoricalBom.applicable_specification.contains(specification.strip()))
    rows = db.scalars(stmt.order_by(HistoricalBom.bom_code, HistoricalBom.line_no).limit(300)).all()
    return render(request, db, "knowledge.html", rows=rows, filters={"query": query, "specification": specification})


@app.post("/knowledge/import")
async def import_knowledge(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    require_permission(user, "knowledge_import")
    filename = Path(file.filename or "history.csv").name
    if Path(filename).suffix.lower() != ".csv":
        set_flash(request, "历史 BOM 导入失败，请检查字段和文件内容", "error")
        return redirect("/knowledge")
    try:
        content = (await file.read()).decode("utf-8-sig")
        rows = parse_csv(content, filename)
    except (UnicodeDecodeError, ValueError):
        set_flash(request, "历史 BOM 导入失败，请检查字段和文件内容", "error")
        return redirect("/knowledge")
    db.add_all(rows)
    log_action(db, user, "import_history_bom", "historical_bom", filename, after={"rows": len(rows)})
    db.commit()
    set_flash(request, f"历史 BOM 导入成功，共 {len(rows)} 行")
    return redirect("/knowledge")


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    require_role(user, "admin")
    users = db.scalars(select(User).order_by(User.id)).all()
    audits = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(100)).all()
    return render(
        request,
        db,
        "admin.html",
        users=users,
        audits=audits,
        config={
            "database": "SQLite（本地演示）",
            "ai_mode": "离线确定性规则",
            "governance": "L1：所有 BOM 结果需人工确认",
            "session_secure": bool(os.getenv("SESSION_SECRET")),
        },
    )


@app.get("/health")
def health():
    return {"status": "ok"}
