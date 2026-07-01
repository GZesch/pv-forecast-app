"""BDEW H25 and transparent ExergyPulse household load profiles.

H25 is a standard profile, not an individual measurement. Its 2018/2019 source
data contains moderate prosumer influence; presence, appliances, heat pumps and
electric vehicles are not identified. The technical comparison year is 2001.
"""

import csv
import hashlib
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from io import TextIOBase
from math import isfinite
from pathlib import Path
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

OFFICIAL_SOURCE_URL = (
    "https://www.bdew.de/media/documents/Kopie_von_Repr%C3%A4sentative_Profile_"
    "BDEW_H25_G25_L25_P25_S25_Ver%C3%B6ffentlichung.xlsx"
)
OFFICIAL_XLSX_SHA256 = "1803D4C612693563A784EB61001E7C58FFD6BD18A6BCA3780F774F3C3459B845"
OFFICIAL_H25_CSV_SHA256 = "83A7F47E3A6BDEC28EF49FC56351542B3CBC13493BD988908B15579D7A6D66B8"
SOURCE_VERSION = "2025-03-17"
SOURCE_NORMALIZATION_KWH = 1_000_000.0
CANONICAL_YEAR = 2001
BERLIN = ZoneInfo("Europe/Berlin")
REQUIRED_COLUMNS = ("month", "day_type", "quarter_hour", "value")


class LoadProfileError(ValueError):
    """Raised when household load-profile inputs are incomplete or invalid."""


class H25DataUnavailableError(LoadProfileError):
    """Raised when validated external H25 data was not supplied."""


class DayType(StrEnum):
    WEEKDAY = "WT"
    SATURDAY = "SA"
    SUNDAY_HOLIDAY = "FT"


class ProfileKind(StrEnum):
    H25 = "h25"
    DAYTIME = "exergypulse_daytime"
    EVENING = "exergypulse_evening"
    FLATTER = "exergypulse_flatter"


@dataclass(frozen=True, slots=True)
class H25Key:
    month: int
    day_type: DayType
    quarter_hour: int


@dataclass(frozen=True, slots=True)
class BDEWH25Data:
    values: dict[H25Key, float]
    unit: str
    normalization_kwh: float
    source_name: str
    source_version: str
    source_url: str
    source_sha256: str

    def value(self, month: int, day_type: DayType, quarter_hour: int) -> float:
        return self.values[H25Key(month, day_type, quarter_hour)]


@dataclass(frozen=True, slots=True)
class LoadProfileMetadata:
    source_type: str
    source_name: str
    source_version: str
    source_url: str
    source_xlsx_sha256: str
    source_csv_sha256: str
    methodological_note: str
    synthetic_parameters: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class LoadProfileResult:
    profile_id: str
    profile_name: str
    timestamps_utc: tuple[datetime, ...]
    hourly_consumption_kwh: tuple[float, ...]
    annual_consumption_kwh: float
    metadata: LoadProfileMetadata


SUPPORTED_STATES = frozenset(
    {"BW", "BY", "BE", "BB", "HB", "HH", "HE", "MV", "NI", "NW",
     "RP", "SL", "SN", "ST", "SH", "TH"}
)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def verify_bdew_h25_file(path: str | Path) -> BDEWH25Data:
    """Verify the external official H25 CSV without exposing its contents."""
    source_path = Path(path)
    if not source_path.is_file():
        raise H25DataUnavailableError(
            "The validated external official H25 CSV file was not found or is not a regular file."
        )
    if sha256_file(source_path) != OFFICIAL_H25_CSV_SHA256:
        raise LoadProfileError(
            "External H25 CSV provenance check failed: its SHA-256 does not "
            "match the validated conversion of the official BDEW workbook."
        )
    with source_path.open(encoding="utf-8", newline="") as source:
        return parse_bdew_h25_csv(
            source, unit="kWh", normalization_kwh=SOURCE_NORMALIZATION_KWH,
            source_name="BDEW H25", source_version=SOURCE_VERSION,
            source_url=OFFICIAL_SOURCE_URL, source_sha256=OFFICIAL_XLSX_SHA256,
        )


def convert_bdew_h25_xlsx(
    input_path: str | Path, output_path: str | Path, *,
    expected_sha256: str = OFFICIAL_XLSX_SHA256,
) -> tuple[str, str]:
    """Convert a validated, local official XLSX to deterministic UTF-8 CSV."""
    input_path, output_path = Path(input_path), Path(output_path)
    source_hash = sha256_file(input_path)
    if source_hash != expected_sha256.upper():
        raise LoadProfileError(
            f"Unexpected H25 XLSX SHA-256: {source_hash}; expected {expected_sha256.upper()}."
        )
    matrix = _read_h25_ooxml(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target, lineterminator="\n")
        writer.writerow(REQUIRED_COLUMNS)
        for month, day_type, quarter_hour, value in matrix:
            writer.writerow((month, day_type, quarter_hour, format(value, ".15g")))
    return source_hash, sha256_file(output_path)


def _read_h25_ooxml(path: Path) -> list[tuple[int, str, int, float]]:
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    with zipfile.ZipFile(path) as archive:
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {item.attrib["Id"]: item.attrib["Target"] for item in rels}
        sheets = {item.attrib["name"]: targets[item.attrib[f"{{{ns['r']}}}id"]]
                  for item in workbook.find("m:sheets", ns)}
        if "H25" not in sheets:
            raise LoadProfileError("The XLSX does not contain an H25 worksheet.")
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.itertext()) for node in root.findall("m:si", ns)]
        target = targets[next(item.attrib[f"{{{ns['r']}}}id"] for item in
                              workbook.find("m:sheets", ns) if item.attrib["name"] == "H25")]
        sheet_path = "xl/" + target.lstrip("/").removeprefix("xl/")
        sheet = ElementTree.fromstring(archive.read(sheet_path))
        cells: dict[str, object] = {}
        for cell in sheet.findall(".//m:c", ns):
            value_node = cell.find("m:v", ns)
            if value_node is None:
                continue
            raw: object = value_node.text or ""
            if cell.attrib.get("t") == "s":
                raw = shared[int(str(raw))]
            else:
                raw = float(str(raw))
            cells[cell.attrib["r"]] = raw
    if cells.get("C1") != "H25" or "1 Mio kWh" not in str(cells.get("E1", "")):
        raise LoadProfileError("H25 identity or 1,000,000 kWh normalization is missing.")
    rows: list[tuple[int, str, int, float]] = []
    for column in range(3, 39):
        month = (column - 3) // 3 + 1
        column_name = _excel_column(column)
        day_type = str(cells.get(f"{column_name}4", ""))
        if day_type not in {item.value for item in DayType}:
            raise LoadProfileError("H25 must contain SA, FT and WT for every month.")
        for quarter_hour, row in enumerate(range(5, 101)):
            value = cells.get(f"{column_name}{row}")
            if not isinstance(value, float) or not isfinite(value) or value < 0:
                raise LoadProfileError("H25 must contain 3,456 finite non-negative values.")
            rows.append((month, day_type, quarter_hour, value))
    if len(rows) != 3456:
        raise LoadProfileError("H25 must contain exactly 3,456 values.")
    return rows


def _excel_column(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def parse_bdew_h25_csv(
    source: TextIOBase, *, unit: str, normalization_kwh: float,
    source_name: str, source_version: str, source_url: str, source_sha256: str,
) -> BDEWH25Data:
    if not unit.strip() or not isfinite(normalization_kwh) or normalization_kwh <= 0:
        raise LoadProfileError("H25 unit and positive normalization must be documented.")
    if any(not item.strip() for item in
           (source_name, source_version, source_url, source_sha256)):
        raise LoadProfileError("H25 source provenance and checksum must be complete.")
    reader = csv.DictReader(source)
    if reader.fieldnames != list(REQUIRED_COLUMNS):
        raise LoadProfileError("Invalid H25 CSV columns.")
    values: dict[H25Key, float] = {}
    for line, row in enumerate(reader, 2):
        try:
            key = H25Key(int(row["month"]), DayType(row["day_type"]),
                         int(row["quarter_hour"]))
            value = float(row["value"])
        except (KeyError, TypeError, ValueError) as exc:
            raise LoadProfileError(f"Invalid H25 CSV line {line}.") from exc
        if not 1 <= key.month <= 12 or not 0 <= key.quarter_hour < 96:
            raise LoadProfileError(f"Invalid H25 key on CSV line {line}.")
        if not isfinite(value) or value < 0:
            raise LoadProfileError(f"Invalid H25 value on CSV line {line}.")
        if key in values:
            raise LoadProfileError(f"Duplicate H25 key on CSV line {line}.")
        values[key] = value
    expected = {H25Key(month, kind, quarter) for month in range(1, 13)
                for kind in DayType for quarter in range(96)}
    if values.keys() != expected:
        raise LoadProfileError(
            "H25 data must contain all 12 months, three day types, and exactly "
            "96 quarter-hours per type-day."
        )
    return BDEWH25Data(values, unit, normalization_kwh, source_name,
                       source_version, source_url, source_sha256)


def bdew_dynamisation_factor(day_of_year: int) -> float:
    """Official H25/H0 polynomial; the factor is rounded to four decimals."""
    if not 1 <= day_of_year <= 366:
        raise LoadProfileError("Day of year must be between 1 and 366.")
    t = float(day_of_year)
    return round(-3.92e-10*t**4 + 3.20e-7*t**3 - 7.02e-5*t**2
                 + 2.10e-3*t + 1.24, 4)


def classify_day(local_date: date, federal_state: str) -> DayType:
    state = federal_state.upper()
    if state not in SUPPORTED_STATES:
        raise LoadProfileError(f"Unsupported German federal state: {federal_state}.")
    if local_date.day in (24, 31) and local_date.month == 12:
        return DayType.SUNDAY_HOLIDAY if local_date.weekday() == 6 else DayType.SATURDAY
    if local_date in _holidays(local_date.year, state) or local_date.weekday() == 6:
        return DayType.SUNDAY_HOLIDAY
    return DayType.SATURDAY if local_date.weekday() == 5 else DayType.WEEKDAY


def _holidays(year: int, state: str) -> set[date]:
    easter = _easter_sunday(year)
    days = {date(year, 1, 1), easter-timedelta(days=2), easter+timedelta(days=1),
            date(year, 5, 1), easter+timedelta(days=39), easter+timedelta(days=50),
            date(year, 10, 3), date(year, 12, 25), date(year, 12, 26)}
    fixed = {
        "BW": ((1, 6), (11, 1)), "BY": ((1, 6), (11, 1)),
        "BE": ((3, 8),), "BB": ((10, 31),), "HB": ((10, 31),),
        "HH": ((10, 31),), "MV": ((3, 8), (10, 31)),
        "NI": ((10, 31),), "NW": ((11, 1),), "RP": ((11, 1),),
        "SL": ((8, 15), (11, 1)), "SN": ((10, 31),),
        "ST": ((1, 6), (10, 31)), "SH": ((10, 31),),
        "TH": ((9, 20), (10, 31)),
    }
    days.update(date(year, month, day) for month, day in fixed.get(state, ()))
    if state in {"BW", "BY", "HE", "NW", "RP", "SL"}:
        days.add(easter + timedelta(days=60))  # Corpus Christi
    if state == "SN":
        nov23 = date(year, 11, 23)
        days.add(nov23 - timedelta(days=(nov23.weekday() - 2) % 7))
    return days


def _easter_sunday(year: int) -> date:
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f, g = (b + 8) // 25, (b - (b + 8) // 25 + 1) // 3
    h = (19*a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2*e + 2*i - h - k) % 7
    m = (a + 11*h + 22*l) // 451
    month = (h + l - 7*m + 114) // 31
    return date(year, month, (h + l - 7*m + 114) % 31 + 1)


def generate_household_load_profile(
    annual_consumption_kwh: float, federal_state: str,
    profile_kind: ProfileKind | str = ProfileKind.H25, *,
    h25_csv_path: str | Path | None = None,
) -> LoadProfileResult:
    if not isfinite(annual_consumption_kwh) or annual_consumption_kwh <= 0:
        raise LoadProfileError("Annual consumption must be positive and finite.")
    try:
        kind = ProfileKind(profile_kind)
    except ValueError as exc:
        raise LoadProfileError(f"Unsupported profile kind: {profile_kind}.") from exc
    state = federal_state.upper()
    if state not in SUPPORTED_STATES:
        raise LoadProfileError(f"Unsupported German federal state: {federal_state}.")
    if h25_csv_path is None:
        raise H25DataUnavailableError(
            "The validated external official H25 CSV file is required."
        )
    h25 = verify_bdew_h25_file(h25_csv_path)
    return _generate_household_load_profile_from_data(
        annual_consumption_kwh, state, kind, h25,
        source_csv_sha256=OFFICIAL_H25_CSV_SHA256,
    )


def _generate_household_load_profile_from_data(
    annual_consumption_kwh: float, federal_state: str,
    profile_kind: ProfileKind | str, h25: BDEWH25Data, *,
    source_csv_sha256: str,
) -> LoadProfileResult:
    """Pure generator for already validated data; tests may inject artificial data."""
    if not isfinite(annual_consumption_kwh) or annual_consumption_kwh <= 0:
        raise LoadProfileError("Annual consumption must be positive and finite.")
    try:
        kind = ProfileKind(profile_kind)
    except ValueError as exc:
        raise LoadProfileError(f"Unsupported profile kind: {profile_kind}.") from exc
    state = federal_state.upper()
    if state not in SUPPORTED_STATES:
        raise LoadProfileError(f"Unsupported German federal state: {federal_state}.")
    timestamps = tuple(datetime(CANONICAL_YEAR, 1, 1, tzinfo=timezone.utc)
                       + timedelta(hours=hour) for hour in range(8760))
    quarters: list[float] = []
    start = timestamps[0]
    for index in range(8760 * 4):
        stamp = start + timedelta(minutes=15 * index)
        local = stamp.astimezone(BERLIN)
        quarter = local.hour * 4 + local.minute // 15
        # Profile day, quarter-hour and dynamisation day all follow German local
        # civil time; the output axis itself remains continuous UTC.
        factor = bdew_dynamisation_factor(local.timetuple().tm_yday)
        quarters.append(round(h25.value(local.month, classify_day(local.date(), state),
                                        quarter) * factor, 3))
    total = sum(quarters)
    if total <= 0:
        raise LoadProfileError("Rolled H25 profile has no positive energy.")
    scale = annual_consumption_kwh / total
    hourly = tuple(sum(quarters[index:index+4]) * scale
                   for index in range(0, len(quarters), 4))
    synthetic = ()
    name = "BDEW H25 – empfohlenes Standardlastprofil"
    is_official = (
        h25.source_sha256 == OFFICIAL_XLSX_SHA256
        and source_csv_sha256 == OFFICIAL_H25_CSV_SHA256
    )
    source_type = "bdew_h25" if is_official else "artificial_test_data"
    if kind != ProfileKind.H25:
        hourly, synthetic = _transform_synthetic(hourly, timestamps, kind)
        name = "Synthetisches ExergyPulse-Szenarioprofil – nicht aus deinen Messdaten abgeleitet."
        source_type = (
            "exergypulse_synthetic" if is_official
            else "exergypulse_synthetic_test_data"
        )
    note = (
        "H25 is not an individual measurement and contains moderate prosumer influence. "
        "The canonical year affects weekday and holiday assignment; quarter-hours are "
        "aggregated to UTC hours. Heat pumps and electric vehicles are not separate."
    )
    metadata = LoadProfileMetadata(
        source_type, h25.source_name, h25.source_version, h25.source_url,
        h25.source_sha256, source_csv_sha256, note, synthetic,
    )
    return LoadProfileResult(kind.value, name, timestamps, hourly,
                             annual_consumption_kwh, metadata)


def _transform_synthetic(
    values: Sequence[float], timestamps: Sequence[datetime], kind: ProfileKind,
) -> tuple[tuple[float, ...], tuple[tuple[str, str], ...]]:
    fraction = 0.15
    if kind == ProfileKind.FLATTER:
        mean = sum(values) / len(values)
        result = tuple((1 - fraction) * value + fraction * mean for value in values)
        return result, (("method", "15% blend toward annual hourly mean"),)
    start_hour, end_hour = ((10, 16) if kind == ProfileKind.DAYTIME else (17, 22))
    target = [start_hour <= stamp.astimezone(BERLIN).hour <= end_hour
              for stamp in timestamps]
    outside_total = sum(value for value, selected in zip(values, target) if not selected)
    inside_total = sum(value for value, selected in zip(values, target) if selected)
    moved = outside_total * fraction
    result = tuple(
        value * (1 - fraction) if not selected else
        value + moved * value / inside_total
        for value, selected in zip(values, target)
    )
    return result, (("shift_fraction", "15%"),
                    ("local_target_window", f"{start_hour:02d}:00-{end_hour+1:02d}:00 Europe/Berlin"))
