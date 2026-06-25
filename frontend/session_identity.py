from uuid import NAMESPACE_URL, UUID, uuid5


DEFAULT_USER_CODE = "demo"


def normalize_user_code(code: str | None) -> str:
    normalized = (code or "").strip().lower()
    return normalized or DEFAULT_USER_CODE


def stable_session_id_from_code(code: str | None) -> UUID:
    normalized = normalize_user_code(code)
    return uuid5(NAMESPACE_URL, f"pv-forecast:{normalized}")
