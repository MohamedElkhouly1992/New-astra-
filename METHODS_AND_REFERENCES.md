# Research status and reproducible methods

Version 0.1, 7 September 2026. **Executable prototype, not a validated building digital twin.**
The Python engine is independently implemented and has not passed ASHRAE 140 testing.
The included EnergyPlus runner is a separate execution utility; no actual building IDF is supplied.

## Equation map

For each zone, the implemented sensible balance is

`C dT/dt = UA_eff (Tout − T) + G − Q_sensible`.

`UA_eff = UA_envelope + rho_air cp_air (V_outdoor(1−eta_sensible)+V_infiltration)`.
The exact constant-input hourly update is `T_free=Tout+(Told−Tout)exp(−UA_eff dt/C)+G(1−exp(−UA_eff dt/C))/UA_eff`.
Ideal sensible demand is the nonnegative removal required to reach the occupied setpoint.
Heat balance formulation is consistent in principle with [EnergyPlus zone integration documentation](https://bigladdersoftware.com/epx/docs/24-2/engineering-reference/basis-for-the-zone-and-air-system-integration.html), but the present single-capacitance approximation omits the detailed surface balances and interzone transfer.

Latent demand uses positive outdoor-to-target humidity-ratio difference at 101325 Pa plus 55 W/person. This is a **steady-state proxy**, not an indoor moisture balance. Occupant sensible gain is assumed 75 W/person. These constants require activity-specific replacement; no claim is made that they describe engineering laboratories.

Chiller power uses `P = Q_available / COP_reference × f_temperature × f_partload × cycling / (1−loss)`.
`f_partload=0.15+0.70 PLR+0.15 PLR²`, evaluated no lower than the specified minimum PLR.
These are **generic illustrative coefficients**, not manufacturer coefficients or a reproduction of EnergyPlus.
EnergyPlus's Electric EIR framework models temperature and part-load effects using performance curves; the intended production model must use the compatible equipment-specific curves. See [EnergyPlus 24.2 Engineering Reference: Chillers, Electric model based on condenser entering temperature](https://bigladdersoftware.com/epx/docs/24-2/engineering-reference/chillers.html#electric-chiller-model-based-on-condenser-entering-temperature).

Water mass flow is `Q_served/(cp_water × deltaT)` with cp_water=4.18 kJ/(kg K). Supply temperature and delta T are prescribed outputs, not dynamic states. The pump power proxy is cubic with a minimum operating flow fraction. No claim of network hydraulic accuracy is made.

Irreversible loss is `1−exp(−k_age × age)` capped at 0.5. Recoverable loss states increase linearly with simulated runtime (fan/pump hours for their respective states), with declared caps. Maintenance multiplies recoverable states by `1−recovery_fraction`; it does not reset irreversible age. **All deterioration coefficients and recovery values are uncalibrated scenario assumptions.**

EnergyPlus provides separate operational fault objects, including chiller and coil fouling and air-filter fouling; use [the operational-fault reference](https://bigladdersoftware.com/epx/docs/24-2/input-output-reference/group-operational-faults.html) to determine compatible fault definitions for a future detailed implementation. Availability of these objects does not establish a universal ageing rate or validate the rates in this prototype.

**Compatibility finding:** the cited 24.2 documentation defines `FaultModel:Fouling:Chiller` for water-cooled condensers. The prior NMU model is described as air-cooled. Therefore that fault object must not be applied directly as a validated air-cooled chiller fouling model. A suitable air-cooled performance modification requires separate manufacturer or experimental evidence and version-specific implementation checks.

## Numerical outputs

The fixed timestep is exactly one hour; therefore each reported hourly kW value integrates numerically to the same value in kWh for that interval. Seasonal COP is **sum of cooling delivered / sum of electric input**, not the arithmetic average of hourly COP. The building peak is the maximum simultaneous building demand; it is not the sum of individual zone maxima. Period EUI is not annualized for shorter runs. Peak load remains a model estimate, not a design sizing result.

Measurement comparison matches exact hourly timestamps and does not fill missing values. RMSE uses n observations, CVRMSE divides RMSE by measured mean, and NMBE uses mean prediction error divided by measured mean. No parameters are fitted in this feature. These metrics alone do not establish guideline compliance, climate independence, or field validation.

## Evidence hierarchy and next gates

1. Verify code invariants: energy balance, capacity limits, zero-fault equivalence, maintenance boundaries, timestamp alignment.
2. Verify actual building inputs and manufacturer curve validity ranges.
3. Run the detailed model, inspect errors, sizing, warmup convergence and timestep sensitivity.
4. Compare the reduced model with independent detailed reruns without fitting on the test periods.
5. Validate faults with component measurements or a relevant independent fault dataset; clean-baseline agreement does not validate degradation.
6. After commissioning, compare with measured HVAC electricity, evaporator flow and temperatures, and representative zone conditions. Align meters, timestamps, controls and weather.
7. Report parameter ranges and sensitivity/uncertainty with documented distributions. Do not optimize unsupported parameters from daily totals.

[EnergyPlus validation and testing documentation](https://bigladdersoftware.com/epx/docs/22-1/tips-and-tricks-using-energyplus/validation-and-testing.html) distinguishes analytical and comparative testing. The fact that an engine is tested does not validate a particular user building model. This prototype has not undergone that standard testing.

## Provenance

- User's latest explicit facts: 17948.4 m², ground+3 floors, 312 spaces, central chiller, BMS not operational.
- Retrieved source: `HVAC_MATLAB_V3_1_NMU.zip`, prior user project, generated 5 September 2026. The included daily reference is copied unchanged from its `NMU_DesignBuilder_Daily_2020_2024.csv`.
- That package's config uses 17994.3 m²: unresolved discrepancy, **not silently calibrated away**.
- Retrieved prior baseline COP=5.5 and chilled water supply=6°C are simulation anchors, not confirmed nameplate measurements.
- Original 2020–2024 daily records are reported as supplied. Original claims of held-out validation and repeated weather are not independently reproduced by this package. None of the historical fit statistics is presented as validation of the new hourly model.
- References above were consulted 7 September 2026. Version 24.2 is a documentation reference, not a claim about the user's installed version.

## Local execution capability

The [official Codex CLI documentation](https://learn.chatgpt.com/docs/codex/cli) describes a local coding agent that can read, change and run code. In a locally authorized session this can support command-line simulation workflows, subject to installed programs, licensing and permissions. Opening a cloud conversation on another device does not connect its local programs. GUI automation and native model execution must be verified separately.
