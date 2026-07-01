import hashlib
import zipfile

import pytest

from backend.pv_economics.load_profiles import LoadProfileError, convert_bdew_h25_xlsx


def _column(number):
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def artificial_xlsx(path, *, missing=False):
    """Build a minimal OOXML fixture with fabricated constant values, not H25 data."""
    strings = ["H25", "normiert auf 1 Mio kWh Jahresverbrauch", "SA", "FT", "WT"]
    shared = "".join(f"<si><t>{value}</t></si>" for value in strings)
    cells = ['<c r="C1" t="s"><v>0</v></c>', '<c r="E1" t="s"><v>1</v></c>']
    for column in range(3, 39):
        col = _column(column)
        cells.append(f'<c r="{col}4" t="s"><v>{2 + (column - 3) % 3}</v></c>')
        for row in range(5, 101):
            if missing and column == 38 and row == 100:
                continue
            cells.append(f'<c r="{col}{row}"><v>{1 + (row - 5) % 4}</v></c>')
    sheet = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row>' + "".join(cells) + '</row></sheetData></worksheet>'
    workbook = '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="H25" sheetId="1" r:id="rId1"/></sheets></workbook>'
    rels = '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>'
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
        archive.writestr("xl/sharedStrings.xml", f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">{shared}</sst>')


def test_converter_is_deterministic_and_reports_hashes(tmp_path):
    source, first, second = tmp_path / "artificial.xlsx", tmp_path / "a.csv", tmp_path / "b.csv"
    artificial_xlsx(source)
    expected = hashlib.sha256(source.read_bytes()).hexdigest().upper()
    source_hash, first_hash = convert_bdew_h25_xlsx(source, first, expected_sha256=expected)
    _, second_hash = convert_bdew_h25_xlsx(source, second, expected_sha256=expected)
    assert source_hash == expected
    assert first_hash == second_hash
    assert first.read_bytes() == second.read_bytes()
    assert len(first.read_text().splitlines()) == 3457


def test_converter_rejects_hash_mismatch_and_incomplete_matrix(tmp_path):
    source = tmp_path / "artificial.xlsx"
    artificial_xlsx(source)
    with pytest.raises(LoadProfileError, match="SHA-256"):
        convert_bdew_h25_xlsx(source, tmp_path / "out.csv", expected_sha256="0" * 64)
    artificial_xlsx(source, missing=True)
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    with pytest.raises(LoadProfileError, match="3,456"):
        convert_bdew_h25_xlsx(source, tmp_path / "out.csv", expected_sha256=expected)
