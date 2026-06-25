from frontend.session_identity import (
    DEFAULT_USER_CODE,
    project_code_from_query_params,
    normalize_user_code,
    shareable_project_url,
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


def test_project_code_is_read_from_query_params_and_normalized() -> None:
    assert (
        project_code_from_query_params({"project": "  Test-Familie  "})
        == "test-familie"
    )
    assert project_code_from_query_params({"project": ["  Demo-Team  "]}) == "demo-team"
    assert project_code_from_query_params({"project": ""}) == DEFAULT_USER_CODE
    assert project_code_from_query_params({}) == DEFAULT_USER_CODE


def test_shareable_project_url_contains_normalized_project_code() -> None:
    assert (
        shareable_project_url("http://128.140.63.146/?old=value", " Test-Familie ")
        == "http://128.140.63.146/?project=test-familie"
    )
