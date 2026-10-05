PERMISSIONS = {
    "buyer": {"upload", "generate", "edit", "batch", "view"},
    "engineer": {"generate", "edit", "confirm", "view", "knowledge_view"},
    "admin": {
        "upload",
        "generate",
        "edit",
        "confirm",
        "batch",
        "view",
        "knowledge_view",
        "knowledge_import",
        "admin",
    },
}


def can(role: str, action: str) -> bool:
    return action in PERMISSIONS.get(role, set())
