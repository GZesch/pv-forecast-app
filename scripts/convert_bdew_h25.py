"""Convert a locally supplied official BDEW workbook to validated H25 CSV."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.pv_economics.load_profiles import convert_bdew_h25_xlsx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_xlsx")
    parser.add_argument("output_csv")
    args = parser.parse_args()
    source_hash, output_hash = convert_bdew_h25_xlsx(
        args.input_xlsx, args.output_csv
    )
    print(f"Original SHA-256: {source_hash}")
    print(f"Output SHA-256:   {output_hash}")


if __name__ == "__main__":
    main()
