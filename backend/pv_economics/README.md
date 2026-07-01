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
