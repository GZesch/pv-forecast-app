# BDEW H25 source-data status

No H25 value table is stored in this directory. Source and converted files are
explicitly ignored by Git and must remain external.

The official BDEW application guide, *Hinweise zu den aktualisierten
Standardlastprofilen Strom*, dated 17 March 2025, was reviewed at:

https://www.bdew.de/media/documents/2025-03-17_AWH_Aktualisierte_SLP_Strom_2025_Ver%C3%B6ffentlichung.pdf

It documents H25's 12 months, three type-days, normalization to 1,000,000 kWh,
required dynamisation, and the moderate prosumer influence of its 2018/2019
source data. The guide does not contain the 3,456 quarter-hour values as a
machine-readable table. The dynamisation formula is graphical in the PDF.

The official workbook was subsequently verified from this BDEW download URL:

https://www.bdew.de/media/documents/Kopie_von_Repr%C3%A4sentative_Profile_BDEW_H25_G25_L25_P25_S25_Ver%C3%B6ffentlichung.xlsx

Verified original SHA-256:
`1803D4C612693563A784EB61001E7C58FFD6BD18A6BCA3780F774F3C3459B845`.

The workbook contains the complete 12 × 3 × 96 H25 matrix and the official
dynamisation polynomial. It contains no explicit redistribution license. For
that reason neither the original workbook nor converted values are committed.

Run the local, network-free converter with explicit paths:

```text
uv run python scripts/convert_bdew_h25.py INPUT.xlsx OUTPUT.csv
```

It verifies the original checksum and workbook structure, creates deterministic
UTF-8 CSV, and prints both checksums. Supply the generated CSV path and printed
CSV checksum explicitly to `generate_household_load_profile`.

Generation remains fail-closed without a validated external CSV. Synthetic
ExergyPulse scenarios are transformations of that validated H25 basis and are
clearly labelled as scenarios rather than measurements.
