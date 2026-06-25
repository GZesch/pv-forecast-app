from uuid import NAMESPACE_URL, UUID, uuid5
from urllib.parse import urlencode, urlsplit, urlunsplit


DEFAULT_USER_CODE = "demo"
PROJECT_QUERY_PARAM = "project"


def normalize_user_code(code: str | None) -> str:
    normalized = (code or "").strip().lower()
    return normalized or DEFAULT_USER_CODE


def stable_session_id_from_code(code: str | None) -> UUID:
    normalized = normalize_user_code(code)
    return uuid5(NAMESPACE_URL, f"pv-forecast:{normalized}")


def project_code_from_query_params(
    query_params: dict[str, str | list[str] | tuple[str, ...]] | None,
) -> str:
    if not query_params:
        return DEFAULT_USER_CODE
    value = query_params.get(PROJECT_QUERY_PARAM)
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    return normalize_user_code(value)


def shareable_project_url(base_url: str, code: str | None) -> str:
    normalized = normalize_user_code(code)
    parts = urlsplit(base_url)
    query = urlencode({PROJECT_QUERY_PARAM: normalized})
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", query, ""))
