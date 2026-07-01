"""Network-free preflight for an externally supplied BDEW H25 CSV."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.pv_economics.load_profiles import LoadProfileError, verify_bdew_h25_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate external BDEW H25 runtime data.")
    parser.add_argument("path", nargs="?", default="/app/runtime-data/bdew_h25.csv")
    args = parser.parse_args(argv)
    try:
        verify_bdew_h25_file(args.path)
    except (LoadProfileError, OSError):
        print("H25-Preflight fehlgeschlagen: Datei fehlt oder ist ungültig.", file=sys.stderr)
        return 1
    print("H25-Preflight erfolgreich.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
