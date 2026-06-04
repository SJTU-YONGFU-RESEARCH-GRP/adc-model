# ngspice testbenches

Open-source SPICE simulations for the configurable ADC using native ngspice
behavioral sources (B-devices).

## Does ngspice use the Verilog-A model?

**Not directly.** The reference model lives in `veriloga/configurable_adc.va` and is
used by:

- **Python** behavioral twin (`src/adc_model/model.py`)
- **Cadence Spectre** (`testbench/spectre/*.scs`)

The **ngspice** path uses a behavioral netlist that follows the **same signal chain**
as the Verilog-A model and Python code. OpenVAF cannot compile the full Verilog-A
source yet (arrays, `cross()`, `transition()`, etc.), so ngspice does not load an
OSDI shared library.

When you run `--ngspice`, the driver renders parameterized netlists into
`<output-dir>/ngspice/` and archives `configurable_adc.va` under
`<output-dir>/veriloga/` for reference.

## Signal chain (aligned with Python / Verilog-A)

| Step | Effect | ngspice implementation |
|------|--------|------------------------|
| 1 | Aperture jitter | PWL stimulus (skipped when thermal/DNL use Python post-process) |
| 2 | Gain + offset | `Bgain` B-source |
| 3 | A2 / A3 nonlinearity | `Bnonlin` on post-gain signal |
| 4 | Thermal noise | Python post-process at clock edges (seeded) |
| 5 | Per-code DNL spread | Python post-process (`build_dnl_profile`) |
| 6 | Quantization | Python post-process, or `Bquant` when noise is off |

## Clock and sampling

- Static: `Vclk` PULSE with `period=1/fs`; Python post-process quantizes once per
  code dwell (`samples_per_code`, effective **16** when noise is enabled).
- Dynamic: edge-aligned export on a uniform `1/fs` grid (matches Python/Spectre FFT
  length). Ideal dynamic runs stop at `v_nl` and quantize in Python like Spectre.

## Prerequisites

- [ngspice](https://ngspice.sourceforge.io/) 36+ (tested with ngspice 42)
- Python environment with this repo installed (`pip install -e .`)

## Quick start

Batch run (all engines):

```bash
./scripts/run_all_simulations.sh --output-root outputs/noise
```

ngspice only:

```bash
python scripts/run_analysis.py --ngspice --output-dir outputs/ngspice
python scripts/run_static.py --ngspice --output-dir outputs/ngspice
python scripts/run_dynamic.py --ngspice --output-dir outputs/ngspice
```

Compare static captures:

```bash
python scripts/compare_static_engines.py --output-root outputs/noise --engines python ngspice
```

## Output layout

```text
outputs/ngspice/
  static_waveform.csv
  dynamic_waveform.csv
  inl_dnl.svg
  spectrum.svg
  ngspice/
    static_inl_dnl.cir         # rendered static testbench
    dynamic_spectrum.cir       # rendered dynamic testbench
    adc_behavioral.inc         # behavioral ADC block snapshot
    includes/                  # reserved for generated includes
  logs/
    ngspice_static.log
    ngspice_dynamic.log
    ngspice_static.wrdata
    ngspice_dynamic.wrdata
  veriloga/
    configurable_adc.va
```

## Fair comparison with Python

```bash
# Quantizer-limited (ideal): Python, ngspice, and Spectre should align on dynamic FFT
./scripts/run_all_simulations.sh --ideal --output-root outputs/ideal
python scripts/compare_static_engines.py --ideal --output-root outputs/ideal

# Default noise: Python and ngspice static/dynamic metrics should match closely
./scripts/run_all_simulations.sh --output-root outputs/noise
python scripts/compare_static_engines.py --output-root outputs/noise
```

Use the same `--noise-seed` for reproducible jitter and DNL (Python and ngspice
post-process share the seed). Spectre uses Verilog-A `$random` and may differ slightly
on noisy static histogram DNL.
