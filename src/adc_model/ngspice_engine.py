"""ngspice testbench generation and execution."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from adc_model.config import AdcConfig, AdcNoiseConfig
from adc_model.io import (
    clock_pulse_waveform,
    prepare_edge_aligned_waveform,
    read_waveform_csv,
    read_waveform_wrdata,
    static_capture_edge_indices,
    uniform_fs_sample_indices,
    write_waveform_csv,
)
from adc_model.model import _fill_sample_hold_codes
from adc_model.noise import (
    apply_analog_front_end_at_edges,
    apply_post_front_end_noise,
    build_dnl_profile,
    quantize_front_end,
)


@dataclass(frozen=True)
class NgspiceRunResult:
    """Artifacts produced by an ngspice simulation."""

    netlist_path: Path
    wrdata_path: Path
    log_path: Path
    csv_path: Path
    include_dir: Path


def _effective_samples_per_code(samples_per_code: int, noise: AdcNoiseConfig) -> int:
    """Match Python static capture depth when noise is enabled."""
    if noise.enabled and samples_per_code < 16:
        return 16
    return samples_per_code


def _apply_input_jitter(
    vin: NDArray[np.float64],
    dt: float,
    noise: AdcNoiseConfig,
    rng: np.random.Generator,
) -> NDArray[np.float64]:
    """Apply aperture jitter to the input waveform before the gain stage."""
    if noise.jitter_rms_s <= 0.0 or len(vin) < 2:
        return vin
    dv_dt = np.gradient(vin, dt)
    jitter_v = noise.jitter_rms_s * dv_dt * rng.normal(0.0, 1.0, len(vin))
    return vin + jitter_v


def _render_pwl_source(
    time: NDArray[np.float64],
    vin: NDArray[np.float64],
) -> str:
    """Render an inline PWL voltage source from sample arrays."""
    points = [f"+ {t:.12e} {v:.12e}" for t, v in zip(time, vin, strict=True)]
    return "Vin vin 0 PWL(\n" + "\n".join(points) + "\n+ )"


def _adc_param_block(cfg: AdcConfig, noise: AdcNoiseConfig) -> str:
    """Return SPICE .param lines for the behavioral ADC."""
    max_code = cfg.max_code
    return f"""
.param BITS={cfg.bits}
.param VREFP={cfg.vrefp}
.param VREFN={cfg.vrefn}
.param MAXCODE={max_code}
.param LSB=({cfg.vrefp}-{cfg.vrefn})/{max_code}
.param GAIN={cfg.gain}
.param OFFSET_V={cfg.offset_v}
.param SIGMA_THERMAL={noise.sigma_thermal_v}
.param NONLINEARITY_A2={noise.nonlinearity_a2}
.param NONLINEARITY_A3={noise.nonlinearity_a3}
.param JITTER_RMS={noise.jitter_rms_s}
.param DNL_SIGMA_LSB={noise.dnl_sigma_lsb}
.param NOISE_SEED={noise.noise_seed}
.param VCM={(cfg.vrefp + cfg.vrefn) / 2.0}
.param VFS={cfg.vrefp - cfg.vrefn}
""".strip()


def _render_dnl_table_include(
    cfg: AdcConfig,
    noise: AdcNoiseConfig,
    include_path: Path,
) -> str:
    """DNL spread is applied in Python post-processing for seed-accurate results."""
    _ = (cfg, noise, include_path)
    return ""


def _needs_python_post_process(noise: AdcNoiseConfig) -> bool:
    """Return True when thermal or DNL must use the seeded Python chain.

    ngspice B-sources cannot reproduce VA ``$random`` per edge with the same seed
    as Python; netlists stop at ``v_nl`` and finish noise/quantize in Python.
    """
    return noise.sigma_thermal_v > 0.0 or noise.dnl_sigma_lsb > 0.0


def _adc_behavioral_block(
    fs_hz: float,
    *,
    stop_before_quantize: bool,
) -> str:
    """Return SPICE B-sources matching the Python / Verilog-A signal chain.

    Order:
      1. Input jitter (applied in the PWL stimulus)
      2. Gain + offset
      3. Nonlinearity (on post-gain signal)
      4. Thermal noise (Python post-process when ``stop_before_quantize``)
      5. Per-code DNL spread (Python post-process when ``stop_before_quantize``)
      6. Quantization (ngspice or Python post-process)
    """
    quantizer = (
        ""
        if stop_before_quantize
        else """
Bquant v_code 0 V={
+ ( V(v_nl) <= VREFN ? 0 :
+   V(v_nl) >= VREFP ? MAXCODE :
+   floor((V(v_nl)-VREFN)/LSB+0.5) ) * LSB
+ }"""
    )
    return f"""
* Behavioral ADC through nonlinearity (matches veriloga/configurable_adc.va)
Bgain v_gain 0 V={{ GAIN*V(vin)+OFFSET_V }}
Bnonlin v_nl 0 V={{
+  V(v_gain) + VFS*(NONLINEARITY_A2*pow((V(v_gain)-VCM)/VFS,2)
+  + NONLINEARITY_A3*pow((V(v_gain)-VCM)/VFS,3))
+}}
{quantizer}
Vclk clk_int 0 PULSE(0 1 0 100p 100p {{0.5/{fs_hz}}} {{1/{fs_hz}}})
""".strip()


def _wrdata_signals(stop_before_quantize: bool) -> str:
    """Return the ngspice ``wrdata`` probe list for a netlist."""
    if stop_before_quantize:
        return "v(vin) v(clk_int) v(v_nl)"
    return "v(vin) v(clk_int) v(v_code)"


def _finalize_ngspice_waveform(
    waveform: dict[str, NDArray[np.float64]],
    cfg: AdcConfig,
    noise: AdcNoiseConfig,
    *,
    static_capture: bool = False,
    max_samples: int | None = None,
    samples_per_code: int = 1,
) -> dict[str, NDArray[np.float64]]:
    """Apply seeded thermal noise, DNL, and quantization after ``v_nl``.

    For static ramps (``static_capture=True``), the analog front end and quantizer
    run once per clock edge (matches Verilog-A), then sample-and-hold fills
    ``v_code``. Dynamic captures use the same per-clock policy.
    """
    if "v_nl" not in waveform:
        return waveform

    rng = np.random.default_rng(noise.noise_seed)
    profile = build_dnl_profile(cfg, noise) if noise.dnl_sigma_lsb > 0.0 else None
    num_samples = len(waveform["v_nl"])

    if static_capture:
        time = waveform["time"]
        export_len = max_samples if max_samples is not None else num_samples
        clk = waveform.get("clk")
        if clk is None or len(clk) != len(time):
            clk = clock_pulse_waveform(time, cfg.fs_hz)
        edge_idx = static_capture_edge_indices(
            export_len,
            clk,
            samples_per_code=samples_per_code,
            time=time,
            fs_hz=cfg.fs_hz,
        )
        dt = 1.0 / cfg.fs_hz
        v_front = apply_analog_front_end_at_edges(
            waveform["vin"],
            edge_idx,
            cfg,
            noise,
            dt=dt,
            rng=rng,
            dnl_profile=profile,
        )
        codes_at_edges = quantize_front_end(v_front, cfg)
        codes = _fill_sample_hold_codes(codes_at_edges, edge_idx, num_samples)
        export_idx = edge_idx[:export_len]
        waveform = {
            "time": time[export_idx],
            "vin": waveform["vin"][export_idx],
            "clk": clock_pulse_waveform(time[export_idx], cfg.fs_hz),
            "v_code": codes[export_idx].astype(np.float64) * cfg.lsb,
            "code": codes[export_idx].astype(np.float64),
        }
    else:
        # Dynamic: one conversion per ``1/fs`` sample on the exported grid.
        time = waveform["time"]
        num_edges = max_samples if max_samples is not None else len(time)
        edge_idx = uniform_fs_sample_indices(num_edges, time, cfg.fs_hz)
        dt = 1.0 / cfg.fs_hz
        v_front = apply_analog_front_end_at_edges(
            waveform["vin"],
            edge_idx,
            cfg,
            noise,
            dt=dt,
            rng=rng,
            dnl_profile=profile,
        )
        codes = quantize_front_end(v_front, cfg)
        waveform = {
            "time": time[edge_idx],
            "vin": waveform["vin"][edge_idx],
            "clk": clock_pulse_waveform(time[edge_idx], cfg.fs_hz),
            "v_code": codes.astype(np.float64) * cfg.lsb,
            "code": codes.astype(np.float64),
        }

    if "v_code" not in waveform:
        waveform["v_code"] = codes.astype(np.float64) * cfg.lsb
    if "code" not in waveform:
        waveform["code"] = codes.astype(np.float64)
    return waveform


def render_static_netlist(
    cfg: AdcConfig,
    noise: AdcNoiseConfig,
    *,
    samples_per_code: int,
    include_dir: Path,
) -> str:
    """Render the ngspice static INL/DNL netlist."""
    samples_per_code = _effective_samples_per_code(samples_per_code, noise)
    num_codes = cfg.num_codes
    num_samples = num_codes * samples_per_code
    dt = 1.0 / cfg.fs_hz
    # Extra clock period so edge-aligned ``v_code`` (+1) stays in range for the last sample.
    t_stop = num_samples * dt
    margin = 0.5 * cfg.lsb
    ramp_start = cfg.vrefn + margin
    ramp_end = cfg.vrefp - margin
    time = np.arange(num_samples, dtype=np.float64) * dt
    vin = np.linspace(ramp_start, ramp_end, num_samples)
    rng = np.random.default_rng(noise.noise_seed)
    if not _needs_python_post_process(noise):
        vin = _apply_input_jitter(vin, dt, noise, rng)
    pwl_source = _render_pwl_source(time, vin)
    dnl_include = _render_dnl_table_include(cfg, noise, include_dir / "dnl_table.inc")
    dnl_lines = f"\n{dnl_include}\n" if dnl_include else ""
    stop_before_quantize = _needs_python_post_process(noise)

    return f"""
* Static INL/DNL testbench for configurable ADC (ngspice behavioral)
* Reference model: veriloga/configurable_adc.va (Spectre AHDL / Python twin)
{_adc_param_block(cfg, noise)}
.param FS={cfg.fs_hz}
.param SAMPLES_PER_CODE={samples_per_code}
.param NUM_SAMPLES={num_samples}
.param DT={dt}
.param TSTOP={t_stop}

.options delmax={dt:.12e} maxstep={dt:.12e}
{dnl_lines}
{pwl_source}
{_adc_behavioral_block(cfg.fs_hz, stop_before_quantize=stop_before_quantize)}

.control
tran {dt:.12e} {t_stop:.12e}
set wr_singlescale
wrdata $wrdata {_wrdata_signals(stop_before_quantize)}
.endc
.end
""".strip()


def render_dynamic_netlist(
    cfg: AdcConfig,
    noise: AdcNoiseConfig,
    *,
    num_samples: int,
    fin_hz: float,
    include_dir: Path,
) -> str:
    """Render the ngspice dynamic spectrum netlist."""
    dt = 1.0 / cfg.fs_hz
    # Extra clock period so edge-aligned export reaches ``num_samples`` after v_code lag.
    t_stop = num_samples * dt
    amplitude = 0.95 * (cfg.vrefp - cfg.vrefn) / 2.0
    mid = 0.5 * (cfg.vrefp + cfg.vrefn)
    time = np.arange(num_samples, dtype=np.float64) * dt
    vin = mid + amplitude * np.sin(2.0 * np.pi * fin_hz * time)
    rng = np.random.default_rng(noise.noise_seed)
    if not _needs_python_post_process(noise):
        vin = _apply_input_jitter(vin, dt, noise, rng)
    pwl_source = _render_pwl_source(time, vin)
    dnl_include = _render_dnl_table_include(cfg, noise, include_dir / "dnl_table.inc")
    dnl_lines = f"\n{dnl_include}\n" if dnl_include else ""
    # Always stop before quantization so dynamic capture matches Python/Spectre edge sampling.
    stop_before_quantize = True

    return f"""
* Dynamic spectrum testbench for configurable ADC (ngspice behavioral)
* Reference model: veriloga/configurable_adc.va (Spectre AHDL / Python twin)
{_adc_param_block(cfg, noise)}
.param FS={cfg.fs_hz}
.param FIN={fin_hz}
.param NUM_SAMPLES={num_samples}
.param DT={dt}
.param TSTOP={t_stop}

.options delmax={dt:.12e} maxstep={dt:.12e}
{dnl_lines}
{pwl_source}
{_adc_behavioral_block(cfg.fs_hz, stop_before_quantize=stop_before_quantize)}

.control
tran {dt:.12e} {t_stop:.12e}
set wr_singlescale
wrdata $wrdata {_wrdata_signals(stop_before_quantize)}
.endc
.end
""".strip()


def write_coherent_sine_pwl(
    path: Path,
    cfg: AdcConfig,
    *,
    num_samples: int,
    fin_hz: float,
) -> Path:
    """Write a coherent sine PWL stimulus for manual ngspice runs."""
    dt = 1.0 / cfg.fs_hz
    time = np.arange(num_samples, dtype=np.float64) * dt
    amplitude = 0.95 * (cfg.vrefp - cfg.vrefn) / 2.0
    mid = 0.5 * (cfg.vrefp + cfg.vrefn)
    vin = mid + amplitude * np.sin(2.0 * np.pi * fin_hz * time)
    lines = [f"{t:.12e} {v:.12e}" for t, v in zip(time, vin, strict=True)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path.resolve()


def _substitute_run_paths(netlist: str, wrdata_path: Path) -> str:
    """Replace runtime placeholders in a generated netlist."""
    return netlist.replace("$wrdata", str(wrdata_path.resolve()))


def run_ngspice_netlist(
    *,
    netlist_text: str,
    netlist_path: Path,
    wrdata_path: Path,
    csv_path: Path,
    log_path: Path,
    fs_hz: float,
    include_dir: Path,
    cfg: AdcConfig,
    noise: AdcNoiseConfig,
    static_capture: bool = False,
    max_samples: int | None = None,
    samples_per_code: int = 1,
) -> NgspiceRunResult:
    """Write, execute, and convert an ngspice netlist."""
    netlist_path.parent.mkdir(parents=True, exist_ok=True)
    include_dir.mkdir(parents=True, exist_ok=True)
    wrdata_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = _substitute_run_paths(netlist_text, wrdata_path)
    netlist_path.write_text(rendered, encoding="utf-8")

    cmd = ["ngspice", "-b", str(netlist_path.resolve())]
    header = [
        f"# ngspice simulation log: {netlist_path.name}",
        f"Generated: {datetime.now(tz=UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"Engine: ngspice behavioral netlist (reference: configurable_adc.va)",
        f"Netlist: {netlist_path.resolve()}",
        f"Includes: {include_dir.resolve()}",
        f"Command: {' '.join(cmd)}",
        "",
    ]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log_file:
        log_file.write("\n".join(header))
        log_file.flush()
        subprocess.run(
            cmd,
            check=True,
            cwd=netlist_path.parent,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )

    stop_before_quantize = _needs_python_post_process(noise)
    # Ideal static keeps B-quantizer in SPICE; noisy/dynamic finish in Python.
    edge_finalize = stop_before_quantize or not static_capture
    analog_signal = "v_nl" if edge_finalize else "v_code"
    waveform = read_waveform_wrdata(wrdata_path, analog_signal=analog_signal)
    if edge_finalize:
        waveform = _finalize_ngspice_waveform(
            waveform,
            cfg,
            noise,
            static_capture=static_capture,
            max_samples=max_samples,
            samples_per_code=samples_per_code if static_capture else 1,
        )
        if not static_capture and max_samples is not None and len(waveform["time"]) > max_samples:
            waveform = {name: values[:max_samples] for name, values in waveform.items()}
    else:
        waveform = prepare_edge_aligned_waveform(waveform, fs_hz, max_samples=max_samples)
    write_waveform_csv(csv_path, waveform)
    return NgspiceRunResult(
        netlist_path=netlist_path.resolve(),
        wrdata_path=wrdata_path.resolve(),
        log_path=log_path.resolve(),
        csv_path=csv_path.resolve(),
        include_dir=include_dir.resolve(),
    )


def run_static_testbench(
    *,
    output_dir: Path,
    cfg: AdcConfig,
    noise: AdcNoiseConfig,
    samples_per_code: int,
    log_path: Path,
) -> dict[str, NDArray[np.float64]]:
    """Run the ngspice static testbench and return waveform data."""
    netlist_dir = output_dir / "ngspice"
    include_dir = netlist_dir / "includes"
    samples_per_code = _effective_samples_per_code(samples_per_code, noise)
    num_samples = cfg.num_codes * samples_per_code
    result = run_ngspice_netlist(
        netlist_text=render_static_netlist(
            cfg,
            noise,
            samples_per_code=samples_per_code,
            include_dir=include_dir,
        ),
        netlist_path=netlist_dir / "static_inl_dnl.cir",
        wrdata_path=output_dir / "logs" / "ngspice_static.wrdata",
        csv_path=output_dir / "static_waveform.csv",
        log_path=log_path,
        fs_hz=cfg.fs_hz,
        include_dir=include_dir,
        cfg=cfg,
        noise=noise,
        static_capture=True,
        max_samples=num_samples,
        samples_per_code=samples_per_code,
    )
    _write_adc_behavioral_snapshot(result.include_dir, cfg.fs_hz, _needs_python_post_process(noise))
    return read_waveform_csv(result.csv_path)


def run_dynamic_testbench(
    *,
    output_dir: Path,
    cfg: AdcConfig,
    noise: AdcNoiseConfig,
    num_samples: int,
    fin_hz: float,
    log_path: Path,
) -> dict[str, NDArray[np.float64]]:
    """Run the ngspice dynamic testbench and return waveform data."""
    netlist_dir = output_dir / "ngspice"
    include_dir = netlist_dir / "includes"
    result = run_ngspice_netlist(
        netlist_text=render_dynamic_netlist(
            cfg,
            noise,
            num_samples=num_samples,
            fin_hz=fin_hz,
            include_dir=include_dir,
        ),
        netlist_path=netlist_dir / "dynamic_spectrum.cir",
        wrdata_path=output_dir / "logs" / "ngspice_dynamic.wrdata",
        csv_path=output_dir / "dynamic_waveform.csv",
        log_path=log_path,
        fs_hz=cfg.fs_hz,
        include_dir=include_dir,
        cfg=cfg,
        noise=noise,
        max_samples=num_samples,
    )
    _write_adc_behavioral_snapshot(result.include_dir, cfg.fs_hz, _needs_python_post_process(noise))
    return read_waveform_csv(result.csv_path)


def _write_adc_behavioral_snapshot(include_dir: Path, fs_hz: float, stop_before_quantize: bool) -> None:
    """Write a human-readable copy of the behavioral ADC block next to the netlist."""
    snapshot = include_dir.parent / "adc_behavioral.inc"
    snapshot.write_text(
        _adc_behavioral_block(fs_hz, stop_before_quantize=stop_before_quantize) + "\n",
        encoding="utf-8",
    )
