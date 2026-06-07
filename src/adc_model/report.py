"""Markdown simulation report generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from adc_model.config import AdcConfig, AdcNoiseConfig
from adc_model.dynamic import DynamicMetrics
from adc_model.simulation_log import SimulationLogPaths, collect_log_files
from adc_model.static import StaticLinearity

SUMMARY_FILENAME = "SUMMARY.md"


@dataclass(frozen=True)
class StaticTestConfig:
    """Static INL/DNL testbench settings."""

    samples_per_code: int
    inl_dnl_method: str
    engine: str


@dataclass(frozen=True)
class DynamicTestConfig:
    """Dynamic FFT testbench settings."""

    num_samples: int
    coherent_bin: int
    fin_hz: float
    engine: str


@dataclass(frozen=True)
class SimulationReport:
    """Complete ADC simulation report payload."""

    adc: AdcConfig
    noise: AdcNoiseConfig
    static_cfg: StaticTestConfig
    dynamic_cfg: DynamicTestConfig
    static_result: StaticLinearity
    dynamic_result: DynamicMetrics
    static_plot: Path
    dynamic_plot: Path
    static_csv: Path
    dynamic_csv: Path
    generated_at: datetime
    log_files: tuple[Path, ...] = ()
    veriloga_model: Path | None = None


def _format_voltage(value_v: float) -> str:
    """Format a voltage value with SI prefix."""
    abs_v = abs(value_v)
    if abs_v >= 1.0:
        return f"{value_v:.6g} V"
    if abs_v >= 1e-3:
        return f"{value_v * 1e3:.6g} mV"
    if abs_v >= 1e-6:
        return f"{value_v * 1e6:.6g} uV"
    return f"{value_v:.6g} V"


def _format_time(value_s: float) -> str:
    """Format a time value with SI prefix."""
    abs_s = abs(value_s)
    if abs_s >= 1.0:
        return f"{value_s:.6g} s"
    if abs_s >= 1e-3:
        return f"{value_s * 1e3:.6g} ms"
    if abs_s >= 1e-6:
        return f"{value_s * 1e6:.6g} us"
    if abs_s >= 1e-9:
        return f"{value_s * 1e9:.6g} ns"
    return f"{value_s * 1e15:.6g} fs"


def _format_frequency(value_hz: float) -> str:
    """Format a frequency value with SI prefix."""
    if abs(value_hz) >= 1e6:
        return f"{value_hz / 1e6:.6g} MHz"
    if abs(value_hz) >= 1e3:
        return f"{value_hz / 1e3:.6g} kHz"
    return f"{value_hz:.6g} Hz"


def _rel_link(report_path: Path, asset_path: Path) -> str:
    """Return a POSIX relative link from the report to an asset."""
    return asset_path.resolve().relative_to(report_path.resolve().parent).as_posix()


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a GitHub-flavored markdown table."""
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def render_report_markdown(report: SimulationReport, report_path: Path) -> str:
    """Render the simulation report as markdown text.

    Args:
        report: Structured simulation results and configuration.
        report_path: Destination path used to compute relative figure links.

    Returns:
        Markdown document contents.
    """
    adc = report.adc
    noise = report.noise
    static = report.static_result
    dynamic = report.dynamic_result
    timestamp = report.generated_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    inl_plot = _rel_link(report_path, report.static_plot)
    spectrum_plot = _rel_link(report_path, report.dynamic_plot)

    adc_rows = [
        ["Resolution", f"{adc.bits} bits"],
        ["Full-scale range", f"{_format_voltage(adc.vrefn)} to {_format_voltage(adc.vrefp)}"],
        ["Ideal LSB", _format_voltage(adc.lsb)],
        ["Sample rate", _format_frequency(adc.fs_hz)],
        ["Gain", f"{adc.gain:.6g}"],
        ["Offset", _format_voltage(adc.offset_v)],
    ]

    if noise.enabled:
        noise_rows = [
            ["Thermal noise (RMS)", _format_voltage(noise.sigma_thermal_v)],
            ["Aperture jitter (RMS)", _format_time(noise.jitter_rms_s)],
            ["Nonlinearity A2", f"{noise.nonlinearity_a2:.6g}"],
            ["Nonlinearity A3", f"{noise.nonlinearity_a3:.6g}"],
            ["DNL spread (RMS)", f"{noise.dnl_sigma_lsb:.6g} LSB"],
            ["Random seed", str(noise.noise_seed)],
        ]
    else:
        noise_rows = [["Mode", "Ideal (quantizer-limited only)"]]

    static_tb_rows = [
        ["Engine", report.static_cfg.engine],
        ["Stimulus", "Slow ramp across full input range"],
        ["Samples per code", str(report.static_cfg.samples_per_code)],
        ["INL/DNL method", report.static_cfg.inl_dnl_method],
        ["Waveform CSV", _rel_link(report_path, report.static_csv)],
    ]

    dynamic_tb_rows = [
        ["Engine", report.dynamic_cfg.engine],
        ["Stimulus", "Coherent full-scale sine"],
        ["Capture length", f"{report.dynamic_cfg.num_samples} samples"],
        ["Coherent bin", str(report.dynamic_cfg.coherent_bin)],
        ["Input tone", _format_frequency(report.dynamic_cfg.fin_hz)],
        ["Waveform CSV", _rel_link(report_path, report.dynamic_csv)],
    ]

    static_metric_rows = [
        ["Max DNL (abs)", f"{static.max_dnl_lsb:.3f} LSB"],
        ["Max INL (abs)", f"{static.max_inl_lsb:.3f} LSB"],
    ]

    dynamic_metric_rows = [
        ["Input tone", _format_frequency(dynamic.fin_hz)],
        ["SNDR", f"{dynamic.sndr_db:.2f} dB"],
        ["SFDR", f"{dynamic.sfdr_db:.2f} dB"],
        ["THD", f"{dynamic.thd_db:.2f} dB"],
        ["ENOB", f"{dynamic.enob_bits:.2f} bits"],
    ]

    harmonic_rows = [
        [
            "Fin" if tone.order == 1 else f"H{tone.order}{'*' if tone.aliased else ''}",
            _format_frequency(tone.freq_hz),
            f"{tone.magnitude_dbfs:.2f} dBFS",
        ]
        for tone in dynamic.harmonics
    ]

    sections = [
        "# ADC Simulation Summary",
        "",
        f"Generated: {timestamp}",
        "",
        "Behavioral simulation of `configurable_adc` with static INL/DNL and dynamic "
        "FFT analysis.",
        "",
        "## Input Configuration",
        "",
        "### ADC Core",
        "",
        _markdown_table(["Parameter", "Value"], adc_rows),
        "",
        "### Noise and Nonlinearity",
        "",
        _markdown_table(["Parameter", "Value"], noise_rows),
        "",
        "### Static Testbench",
        "",
        _markdown_table(["Parameter", "Value"], static_tb_rows),
        "",
        "### Dynamic Testbench",
        "",
        _markdown_table(["Parameter", "Value"], dynamic_tb_rows),
        "",
        "## Static Linearity Results",
        "",
        _markdown_table(["Metric", "Value"], static_metric_rows),
        "",
        f"![INL/DNL plot]({inl_plot})",
        "",
        "## Dynamic Spectrum Results",
        "",
        _markdown_table(["Metric", "Value"], dynamic_metric_rows),
        "",
        "### Identified Harmonics",
        "",
        _markdown_table(["Tone", "Frequency", "Magnitude"], harmonic_rows),
        "",
        "Aliased harmonics are marked with `*`.",
        "",
        f"![Dynamic spectrum]({spectrum_plot})",
        "",
        "## Output Files",
        "",
    ]

    artifact_rows = [
        ["Static waveform", _rel_link(report_path, report.static_csv)],
        ["INL/DNL figure", inl_plot],
        ["Dynamic waveform", _rel_link(report_path, report.dynamic_csv)],
        ["Spectrum figure", spectrum_plot],
    ]
    if report.veriloga_model is not None and report.veriloga_model.is_file():
        artifact_rows.append(
            ["Verilog-A model snapshot", _rel_link(report_path, report.veriloga_model)]
        )
    for log_file in report.log_files:
        artifact_rows.append(["Simulation log", _rel_link(report_path, log_file)])

    sections.extend(
        [
            _markdown_table(["Artifact", "Path"], artifact_rows),
            "",
        ]
    )
    return "\n".join(sections)


def write_simulation_summary(
    *,
    output_dir: Path,
    adc: AdcConfig,
    noise: AdcNoiseConfig,
    static_cfg: StaticTestConfig,
    dynamic_cfg: DynamicTestConfig,
    static_result: StaticLinearity,
    dynamic_result: DynamicMetrics,
    simulator: str,
    log_paths: SimulationLogPaths,
    veriloga_model: Path | None = None,
    summary_path: Path | None = None,
    generated_at: datetime | None = None,
) -> Path:
    """Build and write SUMMARY.md for a completed static + dynamic run.

    Args:
        output_dir: Directory containing waveforms, figures, and logs.
        adc: ADC core configuration.
        noise: Noise and nonlinearity configuration.
        static_cfg: Static testbench settings.
        dynamic_cfg: Dynamic testbench settings.
        static_result: Computed static INL/DNL metrics.
        dynamic_result: Computed dynamic FFT metrics.
        simulator: Engine identifier (``python``, ``ngspice``, or ``spectre``).
        log_paths: Prepared log directory layout for the output folder.
        veriloga_model: Optional archived Verilog-A model path.
        summary_path: Destination markdown path (default: ``output_dir/SUMMARY.md``).
        generated_at: Report timestamp (default: current UTC time).

    Returns:
        Absolute path to the written summary file.
    """
    destination = summary_path or (output_dir / SUMMARY_FILENAME)
    report = SimulationReport(
        adc=adc,
        noise=noise,
        static_cfg=static_cfg,
        dynamic_cfg=dynamic_cfg,
        static_result=static_result,
        dynamic_result=dynamic_result,
        static_plot=output_dir / "inl_dnl.svg",
        dynamic_plot=output_dir / "spectrum.svg",
        static_csv=output_dir / "static_waveform.csv",
        dynamic_csv=output_dir / "dynamic_waveform.csv",
        generated_at=generated_at or datetime.now(tz=timezone.utc),
        log_files=collect_log_files(log_paths, simulator=simulator),
        veriloga_model=veriloga_model,
    )
    return write_report(report, destination)


def write_report(report: SimulationReport, report_path: Path) -> Path:
    """Write the markdown report to disk.

    Args:
        report: Structured simulation results and configuration.
        report_path: Destination markdown path.

    Returns:
        Absolute path to the written report.
    """
    report_path.parent.mkdir(parents=True, exist_ok=True)
    markdown = render_report_markdown(report, report_path)
    report_path.write_text(markdown, encoding="utf-8")
    return report_path.resolve()
