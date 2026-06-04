# adc-model

[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-green?logo=creativecommons&logoColor=white)](https://creativecommons.org/licenses/by/4.0/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776ab.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-0.1.0-blue?logo=semver&logoColor=white)](https://github.com/SJTU-YONGFU-RESEARCH-GRP/adc-model)

**adc-model** provides a configurable ADC behavioral model, SPICE testbenches, and analysis scripts for static INL/DNL and dynamic FFT characterization.

**Repository:** [SJTU-YONGFU-RESEARCH-GRP/adc-model](https://github.com/SJTU-YONGFU-RESEARCH-GRP/adc-model)

- **License:** CC BY 4.0 (see [LICENSE](LICENSE))
- **Entry points:** `scripts/run_all_simulations.sh`, `scripts/compare_static_engines.py`, `scripts/run_analysis.py`, `scripts/run_static.py`, `scripts/run_dynamic.py`
- **Simulators:** Python behavioral model (default), Cadence Spectre, ngspice

## Table of contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
  - [Run all six simulations](#run-all-six-simulations)
  - [Compare static engines](#compare-static-engines)
  - [Full analysis report](#full-analysis-report)
  - [Static INL/DNL only](#static-inldnl-only)
  - [Dynamic spectrum only](#dynamic-spectrum-only)
- [CLI reference](#cli-reference)
- [Python API](#python-api)
- [Simulation engines](#simulation-engines)
  - [Cross-engine agreement and discrepancies](#cross-engine-agreement-and-discrepancies)
- [Project layout](#project-layout)
- [Development](#development)
- [License](#license)

## Features

| Area | Description |
| --- | --- |
| **Behavioral model** | Python twin of `veriloga/configurable_adc.va` — gain/offset mismatch, thermal noise, aperture jitter, A2/A3 nonlinearity, per-code DNL spread |
| **Static testbench** | Slow ramp stimulus, histogram INL/DNL, SVG plots |
| **Dynamic testbench** | Coherent sine capture, FFT metrics (SNDR, SFDR, THD, ENOB, harmonics), spectrum SVG |
| **Multi-engine** | Run the same testbenches in Python, Cadence Spectre, or ngspice behavioral netlists |
| **Clock alignment** | `1/fs` pulse clock; one sample per rising edge (dense transients downsampled to match Verilog-A `@(cross(clk))`) |
| **Reporting** | `REPORT.md` with configuration tables, metrics, and figure links |

## Requirements

- **Python** 3.10 or newer
- **Runtime:** NumPy, Matplotlib (installed automatically)
- **Optional — Spectre:** Cadence Spectre with Verilog-A (AHDL) support
- **Optional — ngspice:** [ngspice](https://ngspice.sourceforge.io/) 36+ (tested with ngspice 42)

## Installation

From the repository root:

```bash
./scripts/install_python.sh
source .venv/bin/activate
```

Or install manually:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Quick start

All commands assume the virtual environment is active and you are in the repository root.

### Run all six simulations

`scripts/run_all_simulations.sh` runs every engine × testbench combination in one pass:

| Engine | Static INL/DNL | Dynamic FFT |
| --- | --- | --- |
| Python | `run_static.py` | `run_dynamic.py` |
| ngspice | same | same |
| Spectre | same | same |

Default output layout (under `outputs/` unless overridden):

```text
outputs/
├── python/
│   ├── static_waveform.csv, inl_dnl.svg
│   ├── dynamic_waveform.csv, spectrum.svg
│   ├── logs/          # *.log (python, spectre, ngspice)
│   └── veriloga/      # archived configurable_adc.va + testbench copies
├── ngspice/           # same CSV/SVG layout + ngspice/*.cir rendered netlists
└── spectre/           # same + logs/*.nutascii, logs/netlists/*.scs, logs/*.ahdlSimDB/
```

Use `--output-root outputs/noise` or `outputs/ideal` to keep noisy and ideal batch runs separate.

```bash
./scripts/run_all_simulations.sh
```

Quantizer-limited baseline (no noise or nonlinearity), separate output tree:

```bash
./scripts/run_all_simulations.sh --ideal --output-root outputs/ideal
```

Skip external simulators when `ngspice` or `spectre` is not installed:

```bash
./scripts/run_all_simulations.sh --skip-missing
```

Forward shared CLI options to every run (must follow `--`):

```bash
./scripts/run_all_simulations.sh -- --bits 12 --fs 2e6
```

| Option | Description |
| --- | --- |
| `--ideal` | Pass `--ideal` to each Python driver |
| `--output-root DIR` | Base directory for `python/`, `ngspice/`, `spectre/` subfolders |
| `--skip-missing` | Run Python only if ngspice/Spectre are absent from `PATH` |
| `-h`, `--help` | Show usage |

Environment variables: `OUTPUT_ROOT` (same as `--output-root`), `VENV_DIR` (Python interpreter under `${VENV_DIR}/bin/python`).

Requires `ngspice` and `spectre` on `PATH` unless `--skip-missing` is set.

### Compare static engines

After `run_all_simulations.sh`, use `scripts/compare_static_engines.py` to print a side-by-side table of static ramp statistics and INL/DNL metrics for each engine under the same `--output-root`. This uses the same ADC settings and INL/DNL method as `run_static.py` (histogram when noise is enabled, transition/`auto` when `--ideal`).

```bash
# Default-noise batch (outputs/noise/{python,ngspice,spectre}/)
python scripts/compare_static_engines.py --output-root outputs/noise

# Ideal batch
python scripts/compare_static_engines.py --ideal --output-root outputs/ideal

# Subset of engines or explicit ramp depth
python scripts/compare_static_engines.py --output-root outputs/noise --engines python spectre
python scripts/compare_static_engines.py --output-root outputs/noise --samples-per-code 4
```

| Option | Description |
| --- | --- |
| `--output-root DIR` | Parent folder with per-engine subdirectories (same as `run_all_simulations.sh`) |
| `--ideal` | Match ideal / quantizer-limited runs |
| `--samples-per-code` | Ramp depth per code (default `4`; effective `16` when noise is on) |
| `--inl-dnl-method` | `auto`, `histogram`, or `transition` (default `auto` = same as `run_static.py`) |
| `--engines` | Space-separated list: `python`, `ngspice`, `spectre` |

The table reports sample count, code-transition count, per-code hit statistics (min/max/mean/std), and max \|DNL\| / \|INL\|. A short **vs python** summary shows deltas to the Python behavioral reference.

Example (default-noise static, from `./scripts/run_all_simulations.sh`):

```text
Engine      Samples  Transitions  Hits mean  Hits std  Max |DNL|  Max |INL|
python        16384         4817      15.87      2.81      1.000      4.441
ngspice       16384         4817      15.87      2.81      1.000      4.441
spectre       16384         1017      15.88      0.73      1.000      4.036
```

See [Cross-engine agreement and discrepancies](#cross-engine-agreement-and-discrepancies) for why Spectre reports far fewer code transitions and how to interpret INL/DNL and FFT deltas. Use `--check-parity` to fail CI when metrics drift beyond scripted tolerances:

```bash
python scripts/compare_static_engines.py --output-root outputs --check-parity
```

### Full analysis report

Run static and dynamic simulations, generate plots, archive logs, and write `REPORT.md`:

```bash
python scripts/run_analysis.py --output-dir outputs/python
```

Use `--ideal` for a quantizer-limited baseline (no noise or nonlinearity):

```bash
python scripts/run_analysis.py --ideal --output-dir outputs/python_ideal
```

### Static INL/DNL only

```bash
python scripts/run_static.py --output-dir outputs/static
```

Analyze an existing waveform CSV (skip simulation):

```bash
python scripts/run_static.py --input outputs/python/static_waveform.csv --output-dir outputs/static
```

### Dynamic spectrum only

```bash
python scripts/run_dynamic.py --output-dir outputs/dynamic
```

Override the input tone frequency or coherent bin:

```bash
python scripts/run_dynamic.py --fin 100000 --num-samples 8192 --output-dir outputs/dynamic
```

## CLI reference

Shared ADC and noise options are available on all three scripts (`run_analysis.py`, `run_static.py`, `run_dynamic.py`).

| Option | Default | Description |
| --- | --- | --- |
| `--bits` | `10` | ADC resolution |
| `--vrefp`, `--vrefn` | `1.0`, `0.0` | Full-scale reference (V) |
| `--gain`, `--offset-v` | `1.01`, `5e-3` | Static gain and offset mismatch |
| `--fs` | `1e6` | Sample rate (Hz) |
| `--ideal` | off | Disable all noise and nonlinearity |
| `--sigma-thermal-v` | `250e-6` | Input-referred thermal noise RMS (V) |
| `--jitter-rms-s` | `500e-15` | Aperture jitter RMS (s) |
| `--nonlinearity-a2`, `--nonlinearity-a3` | `0.0`, `-0.002` | Second- and third-order nonlinearity |
| `--dnl-sigma-lsb` | `0.08` | Per-code DNL spread (LSB RMS) |
| `--noise-seed` | `1` | Random seed |
| `--simulator` | `python` | Engine: `python`, `spectre`, or `ngspice` |
| `--spectre` | — | Alias for `--simulator spectre` |
| `--ngspice` | — | Alias for `--simulator ngspice` |

Script-specific options:

| Script | Option | Default | Description |
| --- | --- | --- | --- |
| `run_static.py` | `--samples-per-code` | `4` | Ramp hits per output code |
| `run_static.py` | `--input` | — | Existing waveform CSV |
| `run_dynamic.py` | `--num-samples` | `8192` | FFT capture length |
| `run_dynamic.py` | `--coherent-bin` | `997` | Coherent FFT bin index |
| `run_dynamic.py` | `--fin` | coherent bin | Input tone frequency (Hz) |
| `run_analysis.py` | `--report` | `<output-dir>/REPORT.md` | Report output path |

## Python API

```python
import numpy as np
from adc_model import AdcConfig, AdcNoiseConfig, compute_inl_dnl, compute_dynamic_metrics
from adc_model import simulate_static, simulate_dynamic

cfg = AdcConfig(bits=10, fs_hz=1e6)
noise = AdcNoiseConfig(sigma_thermal_v=250e-6, dnl_sigma_lsb=0.08)

static = simulate_static(cfg, samples_per_code=4, noise=noise)
codes = static["code"].astype(np.int64)
linearity = compute_inl_dnl(static["vin"], codes, cfg)

dynamic = simulate_dynamic(cfg, num_samples=8192, fin_hz=121_704.0, noise=noise)
dyn_codes = dynamic["code"].astype(np.int64)
metrics = compute_dynamic_metrics(dyn_codes, cfg, fin_hz=121_704.0)
```

`simulate_static` / `simulate_dynamic` return dicts with keys `time`, `vin`, `clk`, `v_code`, and `code`.
Public exports are listed in `adc_model.__all__`.

## Simulation engines

| Engine | Flag | Notes |
| --- | --- | --- |
| **Python** | `--simulator python` (default) | Behavioral twin of `veriloga/configurable_adc.va`; reference for metrics and regression |
| **Spectre** | `--spectre` | Python driver renders netlists and runs Spectre in `<output-dir>/logs/`; AHDL cache (`*.ahdlSimDB/`) stays out of the repo root |
| **ngspice** | `--ngspice` | PULSE `1/fs` clock netlists; thermal noise and per-code DNL are applied in Python at clock edges with the same `noise_seed` when those effects are enabled |

### Cross-engine agreement and discrepancies

All engines share the same CLI defaults (`--gain 1.01`, `--offset-v 5e-3`, noise on unless `--ideal`), per-clock sampling aligned with `configurable_adc.va` (`@(cross(clk))`), and the same post-simulation analysis (`compute_inl_dnl`, `compute_dynamic_metrics`). Differences come from **how** each engine produces the waveform CSV, not from different metric formulas.

#### Default-noise batch (representative)

Running `./scripts/run_all_simulations.sh` (output under `outputs/`) with ngspice and Spectre on `PATH` yields:

| Test | Python | ngspice | Spectre |
| --- | --- | --- | --- |
| Static max \|DNL\| | 1.000 LSB | 1.000 LSB | 1.000 LSB |
| Static max \|INL\| | 4.441 LSB | 4.441 LSB | 4.036 LSB |
| Dynamic SNDR | 58.92 dB | 58.93 dB | 61.10 dB |
| Dynamic SFDR | 85.66 dB | 85.80 dB | 83.45 dB |
| Dynamic ENOB | 9.50 bits | 9.50 bits | 9.86 bits |
| Input tone `Fin` | 0.121704 MHz | same | same |

`Fin` is the coherent bin default: `997 × fs / 8192` at `fs = 1 MHz`.

#### Python and ngspice — near-identical

For the default-noise configuration, **Python and ngspice should match to numerical noise**:

- **Static:** identical sample counts, code-transition counts, hit statistics, and max \|DNL\| / \|INL\| (see `compare_static_engines.py` table above).
- **Dynamic:** SNDR/ENOB within ~0.01 dB / 0.01 bit; SFDR may differ by a few tenths of a dB from FFT numerics.

ngspice runs the behavioral netlist in SPICE, but when thermal noise or DNL spread is enabled it **re-applies those mechanisms in Python** at clock edges using the same `noise_seed` as the Python model. That hybrid path is intentional so open-source regression stays deterministic and aligned with `tests/test_model_parity.py`.

Treat **Python as the golden reference** for CI and algorithm work; use ngspice to validate the exported netlist and PULSE clock wiring.

#### Spectre — expected static gaps

Spectre often **agrees on max \|DNL\|** but **disagrees on static shape metrics** versus Python:

| Observation | Typical cause |
| --- | --- |
| Far fewer **code transitions** on the ramp (e.g. ~1000 vs ~4800) | Verilog-A `$random` and AHDL event scheduling differ from NumPy; transition detection on the exported CSV sees fewer bin crossings even when total samples match |
| Lower **hits std** per code | Smoother per-code histogram occupancy → often **lower reported max \|INL\|** (~0.4 LSB in the table above) with the same worst \|DNL\| |
| Same **max \|DNL\|** (e.g. 1.000 LSB) | Usually a ramp edge / thin-bin artifact shared across engines, not proof of bit-exact code profiles |

Noisy static INL/DNL uses the **histogram** method (same as `run_static.py` when noise is enabled). Spectre is still useful for sign-off on `configurable_adc.va` and Spectre netlists; do not expect bit-exact INL curves next to Python.

`compare_static_engines.py --check-parity` enforces:

| vs Python | \|DNL\| | \|INL\| | Transitions |
| --- | --- | --- | --- |
| ngspice | ≤ 0.02 LSB | ≤ 0.02 LSB | ratio 0.98–1.02 |
| spectre | ≤ 0.02 LSB | ≤ 0.5 LSB | not checked |

#### Spectre — expected dynamic gaps

Dynamic metrics are computed from the **same FFT pipeline** on each engine’s CSV, but the captured codes differ slightly:

- **SNDR / ENOB** can be **~2 dB higher** on Spectre (less in-band noise power in the FFT) while **SFDR** can be **~2 dB lower** (spur energy counted differently). THD usually stays within ~1 dB.
- This is **normal** for a noisy, nonlinear 10-bit model: use Python/ngspice for tight regression; use Spectre to confirm the VA dynamic testbench is in the right ballpark.

#### Interpreting large static INL

With default mismatch (`gain = 1.01`, `offset_v = 5 mV` on a 1 V full-scale 10-bit ADC), **max \|INL\| ≈ 4+ LSB** is dominated by gain/offset error, not the 0.08 LSB DNL spread alone. Reducing mismatch or using `--ideal` collapses INL toward the quantizer-limited case.

#### Ideal (`--ideal`) baseline

Quantizer-limited runs disable thermal noise, jitter, nonlinearity, and DNL spread:

```bash
./scripts/run_all_simulations.sh --ideal --output-root outputs/ideal
```

Expect roughly **~0.25 LSB max \|DNL\|** on static tests and **~61.5 dB SNDR** on dynamic tests across engines, with smaller spread than the noisy batch above.

#### Which engine when

| Goal | Engine |
| --- | --- |
| Regression, API, fast iteration | Python |
| Open-source SPICE netlist check | ngspice |
| Cadence VA / Spectre sign-off | Spectre |
| Strict metric parity | Python vs ngspice; use `--check-parity` for automated static checks |

Detailed engine setup and netlist notes:

- [testbench/spectre/README.md](testbench/spectre/README.md) — Cadence Spectre and Verilog-A
- [testbench/ngspice/README.md](testbench/ngspice/README.md) — Open-source ngspice behavioral netlists

Example with ngspice:

```bash
python scripts/run_analysis.py --ngspice --output-dir outputs/ngspice
```

## Project layout

```text
adc-model/
├── LICENSE
├── README.md
├── pyproject.toml
├── scripts/
│   ├── install_python.sh      # Create venv and editable install
│   ├── run_all_simulations.sh     # All engines: static + dynamic (6 runs)
│   ├── compare_static_engines.py  # Static waveform comparison table
│   ├── run_analysis.py            # Static + dynamic + REPORT.md
│   ├── run_static.py          # INL/DNL testbench
│   └── run_dynamic.py         # FFT spectrum testbench
├── src/adc_model/             # Installable Python package
│   ├── model.py               # Behavioral ADC (matches Verilog-A)
│   ├── io.py                  # Clock waveforms and edge-aligned downsampling
│   ├── static.py              # INL/DNL analysis and plots
│   ├── static_compare.py      # Multi-engine static comparison (CLI backend)
│   ├── dynamic.py             # FFT metrics and spectrum plots
│   ├── spectre_engine.py      # Spectre driver helpers
│   ├── ngspice_engine.py      # ngspice netlist rendering
│   └── report.py              # REPORT.md generation
├── testbench/
│   ├── spectre/               # Spectre netlists (.scs)
│   └── ngspice/               # ngspice netlists (.cir)
├── veriloga/
│   ├── configurable_adc.va    # Reference Verilog-A model
│   └── ti_channel_adc.va
└── tests/                     # pytest suite
```

Simulation outputs (CSV waveforms, SVG figures, logs, rendered netlists) are written to `--output-dir` and are gitignored under `outputs/`. Spectre AHDL debris (`status`, `*.ahdlSimDB/` in the repo root) is listed in `.gitignore` and cleaned when using the Python Spectre driver.

## Development

```bash
source .venv/bin/activate
pytest
ruff check .
```

Install without dev dependencies:

```bash
./scripts/install_python.sh --no-dev
```

## License

Licensed under [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/). See [LICENSE](LICENSE).

Third-party tools (Cadence Spectre, ngspice) are subject to their own license terms.
