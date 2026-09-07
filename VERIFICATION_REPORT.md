# Execution verification — 7 September 2026

Seven automated checks passed (`python -m unittest discover -p test_core.py -v`):

- Hourly component electricity balances and simultaneous building demand.
- Zero-ageing configuration equals the healthy comparator.
- A pure COP loss increases chiller electricity at equal delivered cooling.
- Capacity-limited service reports unmet demand; maintenance does not erase chronological wear.
- Exact-timestamp comparison reproduces zero error for identical measurement input.
- Invalid configuration values are rejected.
- Invalid zone area sums and nonconsecutive weather timestamps are rejected.

The annual default demonstration completed **five scenarios × 8,760 hourly steps**, each with 312 zone summaries. All exported hourly numeric outputs were finite. Electric component balance and cooling service bounds passed across the entire annual output.

The default demonstration has assumed equal zones, synthetic weather and unverified equipment capacities. It has substantial unmet cooling; it is **not a sizing recommendation or a case-study result**. S2 and S3 do not trigger in this default run because their thresholds are not reached. No interventions or apparent savings were manufactured to make these policies look better.

Syntax compilation passed for the desktop app, engine, CLI and EnergyPlus utility. The native Tk desktop GUI was **not interactively tested** because the execution environment has no graphical display. Windows launcher, MATLAB launcher and external EnergyPlus execution remain untested on the user's machine. MATLAB/Simulink and EnergyPlus were not used to produce these results.

These checks verify selected code properties. They do **not** establish ASHRAE testing compliance, field calibration, component fault validation, or publication readiness. See `METHODS_AND_REFERENCES.md` and `README_AR.txt` for required research inputs and validation gates.
