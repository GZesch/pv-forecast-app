# BDEW H25 source-data status

No H25 value table is stored in this directory.

The official BDEW application guide, *Hinweise zu den aktualisierten
Standardlastprofilen Strom*, dated 17 March 2025, was reviewed at:

https://www.bdew.de/media/documents/2025-03-17_AWH_Aktualisierte_SLP_Strom_2025_Ver%C3%B6ffentlichung.pdf

It documents H25's 12 months, three type-days, normalization to 1,000,000 kWh,
required dynamisation, and the moderate prosumer influence of its 2018/2019
source data. The guide does not contain the 3,456 quarter-hour values as a
machine-readable table. The dynamisation formula is graphical in the PDF.

As of 1 July 2026, no official BDEW H25 value file with sufficiently clear
redistribution or licensing terms could be located. Therefore no values were
copied from third-party websites, screenshots, diagrams, academic appendices,
or the old H0 profile. No checksum is recorded because no source data file was
accepted or transformed.

`load_profiles.parse_bdew_h25_csv` defines and validates the future normalized
CSV format. Before adding a data file, record its exact official download URL,
publication version, original format, license/usage terms, original SHA-256,
conversion procedure, and converted-file SHA-256 here. The official formula
and its rounding rules must likewise be transcribed from a verifiable original.

Until then, generation deliberately raises `H25DataUnavailableError`. This also
prevents synthetic ExergyPulse scenarios from being presented as H25-derived.
