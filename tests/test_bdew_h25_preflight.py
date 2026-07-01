from pathlib import Path

import pytest

import scripts.verify_bdew_h25 as cli
from backend.pv_economics import load_profiles
from backend.pv_economics.load_profiles import (
    H25DataUnavailableError, LoadProfileError, verify_bdew_h25_file,
)


def test_missing_file_fails_closed(tmp_path):
    with pytest.raises(H25DataUnavailableError):
        verify_bdew_h25_file(tmp_path / "missing.csv")


def test_wrong_checksum_is_rejected(tmp_path):
    path = tmp_path / "artificial.csv"
    path.write_text("clearly synthetic test data", encoding="utf-8")
    with pytest.raises(LoadProfileError, match="provenance check failed"):
        verify_bdew_h25_file(path)


def test_invalid_csv_is_rejected_after_checksum(monkeypatch, tmp_path):
    path = tmp_path / "artificial.csv"
    path.write_text("invalid,synthetic,csv", encoding="utf-8")
    monkeypatch.setattr(load_profiles, "sha256_file",
                        lambda unused: load_profiles.OFFICIAL_H25_CSV_SHA256)
    with pytest.raises(LoadProfileError):
        verify_bdew_h25_file(path)


def test_successful_verifier_path_with_artificial_fixture(monkeypatch, tmp_path):
    path = tmp_path / "artificial.csv"
    path.write_text("clearly synthetic fixture", encoding="utf-8")
    marker = object()
    monkeypatch.setattr(load_profiles, "sha256_file",
                        lambda unused: load_profiles.OFFICIAL_H25_CSV_SHA256)
    monkeypatch.setattr(load_profiles, "parse_bdew_h25_csv",
                        lambda source, **kwargs: marker)
    assert verify_bdew_h25_file(path) is marker


def test_successful_cli_path_uses_verifier_without_printing_data(monkeypatch, tmp_path, capsys):
    path = tmp_path / "artificial.csv"
    secret = "SYNTHETIC-CONTENT-MUST-NOT-BE-PRINTED"
    path.write_text(secret, encoding="utf-8")
    called: list[Path] = []
    monkeypatch.setattr(cli, "verify_bdew_h25_file", lambda value: called.append(Path(value)))
    assert cli.main([str(path)]) == 0
    output = capsys.readouterr()
    assert called == [path]
    assert "erfolgreich" in output.out
    assert secret not in output.out + output.err


def test_failed_cli_does_not_print_exception_or_contents(monkeypatch, capsys):
    secret = "SYNTHETIC-PRIVATE-ROW"
    def fail(unused):
        raise LoadProfileError(secret)
    monkeypatch.setattr(cli, "verify_bdew_h25_file", fail)
    assert cli.main(["missing.csv"]) == 1
    output = capsys.readouterr()
    assert "fehlgeschlagen" in output.err
    assert secret not in output.out + output.err
