from frontend.session_identity import (
    DEFAULT_USER_CODE,
    normalize_user_code,
    stable_session_id_from_code,
)


def test_same_user_code_creates_same_stable_session_id() -> None:
    assert stable_session_id_from_code("mein-projekt") == stable_session_id_from_code(
        "mein-projekt"
    )


def test_user_code_is_normalized_before_session_id_is_created() -> None:
    assert stable_session_id_from_code("  Mein-Projekt  ") == stable_session_id_from_code(
        "mein-projekt"
    )
    assert normalize_user_code("   ") == DEFAULT_USER_CODE
    assert stable_session_id_from_code("") == stable_session_id_from_code(
        DEFAULT_USER_CODE
    )


def test_different_user_codes_create_different_session_ids() -> None:
    assert stable_session_id_from_code("projekt-a") != stable_session_id_from_code(
        "projekt-b"
    )
