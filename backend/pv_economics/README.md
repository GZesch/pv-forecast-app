# PV economics developer notes

`POST /pv-economics/calculate` is stateless and requires no session header. It
accepts coordinates, household/profile assumptions, one or more PV surfaces,
an optional battery, explicit prices and a commissioning date. The response
contains annual aggregates and cashflows, never the full hourly arrays.

H25 remains external. Set `BDEW_H25_CSV_PATH` to the deterministic CSV produced
by `scripts/convert_bdew_h25.py`; its fixed checksum is verified by the domain.

EEG tariff data version `BNetzA-2026-02-01` covers building and noise-barrier
systems up to 100 kW commissioned from 1 February through 31 July 2026 under
surplus feed-in. Source:
https://www.bundesnetzagentur.de/DE/Fachthemen/ElektrizitaetundGas/ErneuerbareEnergien/EEG_Foerderung/start.html

Defaults are versioned in `defaults.py`. They are model assumptions unless a
primary source is named. Full feed-in, direct marketing, tenant electricity,
financing, taxes and subsidies are outside this API. The base case is unlimited;
the response separately reports a first-year 60% feed-in-limit comparison.

## Optional historical weather sensitivity

`include_weather_sensitivity=true` adds three weather-only scenarios derived
from complete real PVGIS 5.3 `seriescalc` years using `PVGIS-SARAH3`. The adapter
requests each PV surface separately because `Gb(i)`, `Gd(i)` and `Gr(i)` are
already plane-of-array components for its tilt and orientation; no second
transposition is applied. Shading reduces only `Gb(i)`. The existing thermal,
PVWatts DC, inverter-loss and AC-clipping path is then reused.

Every accepted source year must be complete and chronological. A leap year is
normalized by removing exactly all 24 hours of 29 February and mapping the
remaining UTC calendar positions to canonical non-leap year 2001. At least ten
complete years are required for every surface. Structurally damaged years fail
the requested sensitivity instead of being silently used.

The total plant's real years are sorted by annual AC production, with calendar
year as deterministic tie-breaker. Low, median and high select nearest ranks
`ceil(0.10*n)`, `ceil(0.50*n)` and `ceil(0.90*n)`. These are observed historical
weather years, not interpolated years, a future forecast or a guarantee.
Degradation, soiling and additional shading assumptions are not mixed into the
weather-year selection. The response contains aggregates only, never the 8,760
hour series. With the flag omitted or false, no historical request is made.
