# External H25 runtime data

Place the externally prepared file `bdew_h25.csv` in this directory. The CSV
is runtime data and is intentionally not tracked by Git or copied into a Docker
image. The repository does not grant or imply redistribution permission for the
official workbook or its converted values.

1. Obtain the official BDEW workbook locally outside the repository.
2. Convert it without network access:

   ```text
   uv run python scripts/convert_bdew_h25.py INPUT.xlsx runtime-data/bdew_h25.csv
   ```

3. Verify the runtime file:

   ```text
   uv run python scripts/verify_bdew_h25.py runtime-data/bdew_h25.csv
   ```

Expected SHA-256 values:

- official XLSX: `1803D4C612693563A784EB61001E7C58FFD6BD18A6BCA3780F774F3C3459B845`
- deterministic CSV: `83A7F47E3A6BDEC28EF49FC56351542B3CBC13493BD988908B15579D7A6D66B8`

Compose mounts this directory read-only at `/app/runtime-data`. Keep
`BDEW_H25_DATA_HOST_DIR` pointed at the host directory; the application reads
`/app/runtime-data/bdew_h25.csv`. A missing or invalid file fails the preflight
and prevents the Next.js calculator from starting, while the backend and the
existing Streamlit forecast remain startable. Missing data must never be
replaced with test data.
