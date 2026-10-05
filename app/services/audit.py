import json

from sqlalchemy.orm import Session

from ..models import AuditLog, User


def log_action(
    db: Session,
    user: User | None,
    action: str,
    object_type: str,
    object_id: int | str,
    before: object | None = None,
    after: object | None = None,
    ip_address: str | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_user_id=user.id if user else None,
            actor_role=user.role if user else "anonymous",
            action=action,
            object_type=object_type,
            object_id=str(object_id),
            before_json=json.dumps(before or {}, ensure_ascii=False),
            after_json=json.dumps(after or {}, ensure_ascii=False),
            ip_address=ip_address,
        )
    )
