# Spectre testbenches

## Single-channel (`configurable_adc`)

Verilog-A simulations for `configurable_adc` using Cadence Spectre.

## Prerequisites

- Cadence Spectre with Verilog-A (AHDL) support
- Python environment with this repo installed (`pip install -e .`)

## Recommended: Python driver

Use the Python scripts so netlists are rendered with your CLI settings, waveforms are
exported to CSV, and Spectre debris stays under the output tree:

```bash
./scripts/run_all_simulations.sh --output-root outputs/noise
python scripts/run_static.py --spectre --output-dir outputs/spectre
python scripts/run_dynamic.py --spectre --output-dir outputs/spectre
```

Compare static results across engines after a batch run:

```bash
python scripts/compare_static_engines.py --output-root outputs/noise
```

### Spectre run directory (Python driver)

The driver runs Spectre in `<output-dir>/logs/` (not the repository root):

| Artifact | Location | Purpose |
|----------|----------|---------|
| `*.nutascii` | `<output-dir>/logs/<test>.nutascii` | Transient waveform export |
| `<test>.ahdlSimDB/` | `<output-dir>/logs/` | Verilog-A compile cache |
| `netlists/<test>.scs` | `<output-dir>/logs/netlists/` | Rendered netlist (absolute `ahdl_include`) |
| `spectre_*.log` | `<output-dir>/logs/` | Captured simulator stdout |

Legacy `status` and `*.ahdlSimDB/` in the **repo root** (from older runs or manual CLI) are
removed automatically when you use the Python driver. You can also delete them manually:

```bash
rm -rf status static_inl_dnl.ahdlSimDB dynamic_spectrum.ahdlSimDB
```

## Manual CLI (optional)

Manual runs from the repository root still work for quick tests:

```bash
spectre testbench/spectre/static_inl_dnl.scs -format nutascii -raw ./static.raw
spectre testbench/spectre/dynamic_spectrum.scs -format nutascii -raw ./dynamic.raw
```

These create `*.ahdlSimDB/` and may create `status` if you pass `+log status` in the
current directory. Prefer the Python driver to keep the repo root clean.

## Static INL/DNL

Run and analyze in one step:

```bash
python scripts/run_static.py --spectre --output-dir outputs/spectre
```

Analyze an existing waveform CSV:

```bash
python scripts/run_static.py --input outputs/spectre/static_waveform.csv --output-dir outputs/spectre
```

## Dynamic spectrum

```bash
python scripts/run_dynamic.py --spectre --output-dir outputs/spectre
```

Analyze an existing CSV:

```bash
python scripts/run_dynamic.py --input outputs/spectre/dynamic_waveform.csv --output-dir outputs/spectre
```

## Clock and sampling

Spectre testbenches use a `1/fs` clock (`period=1/fs`, 50 % duty) with `maxstep=0.25/fs`.
The Python driver downsamples dense nutascii output to one sample per clock edge (rising
`clk` plus one-point `v_code` settle delay), matching `@(cross(clk))` in
`veriloga/configurable_adc.va`.

## Tunable parameters

Rendered netlists override the `parameters` block from the templates. You can also edit
`testbench/spectre/*.scs` directly:

| Parameter | Purpose |
|-----------|---------|
| `bits` | ADC resolution |
| `gain`, `offset_v` | Static gain and offset mismatch |
| `fs` | Sample rate |
| `samples_per_code` | Static ramp clocks per code (effective `16` when noise is on) |
| `sigma_thermal` | Input-referred RMS noise (V) |
| `jitter_rms` | Aperture jitter RMS (s) |
| `nonlinearity_a2/a3` | Polynomial nonlinearity vs full-scale |
| `dnl_sigma_lsb` | Per-code comparator spread (LSB RMS) |
| `coherent_bin` | FFT bin for dynamic test (dynamic only) |

Set all noise parameters to `0` for ideal quantizer-limited simulation (`--ideal`).

## Simulator selection

| Engine | Flag | Notes |
|--------|------|-------|
| Python (default) | *(none)* | Fast behavioral twin; matches VA signal chain |
| Cadence Spectre | `--spectre` | Verilog-A AHDL; artifacts under `<output-dir>/logs/` |
| ngspice | `--ngspice` | Open-source behavioral netlists |

See [testbench/ngspice/README.md](../ngspice/README.md) for ngspice setup and parity notes.

## Python-only fallback

If Spectre is unavailable:

```bash
python scripts/run_static.py
python scripts/run_dynamic.py
```

Use `--ideal` for quantizer-limited behavior (~61.5 dB SNDR, 10-bit coherent tone).
Default settings add thermal noise, jitter, DNL spread, and third-order nonlinearity.

## Output layout (single `--output-dir`)

```text
outputs/spectre/
  static_waveform.csv
  dynamic_waveform.csv
  inl_dnl.svg
  spectrum.svg
  logs/
    spectre_static.log
    spectre_dynamic.log
    static_inl_dnl.nutascii
    dynamic_spectrum.nutascii
    static_inl_dnl.ahdlSimDB/    # VA compile cache (safe to delete)
    netlists/
      static_inl_dnl.scs
      dynamic_spectrum.scs
  veriloga/
    configurable_adc.va
    adc_include.scs
    static_inl_dnl.scs
    dynamic_spectrum.scs
```

## Full analysis run

```bash
python scripts/run_analysis.py --spectre --output-dir outputs/spectre
python scripts/run_analysis.py --ideal --output-dir outputs/ideal_spectre
```

For individual tests only, use `scripts/run_static.py` or `scripts/run_dynamic.py`.
