"""Simulation logging and Verilog-A artifact archival."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from adc_model.config import AdcConfig, AdcNoiseConfig


@dataclass(frozen=True)
class SimulationLogPaths:
    """Paths to simulation logs and archived model files."""

    logs_dir: Path
    veriloga_dir: Path
    python_static_log: Path
    python_dynamic_log: Path
    spectre_static_log: Path
    spectre_dynamic_log: Path
    ngspice_static_log: Path
    ngspice_dynamic_log: Path
    ngspice_dir: Path
    veriloga_model: Path


def prepare_output_dirs(output_dir: Path) -> SimulationLogPaths:
    """Create log, Verilog-A, and ngspice directories under the output folder."""
    logs_dir = output_dir / "logs"
    veriloga_dir = output_dir / "veriloga"
    ngspice_dir = output_dir / "ngspice"
    logs_dir.mkdir(parents=True, exist_ok=True)
    veriloga_dir.mkdir(parents=True, exist_ok=True)
    ngspice_dir.mkdir(parents=True, exist_ok=True)
    return SimulationLogPaths(
        logs_dir=logs_dir,
        veriloga_dir=veriloga_dir,
        ngspice_dir=ngspice_dir,
        python_static_log=logs_dir / "python_static.log",
        python_dynamic_log=logs_dir / "python_dynamic.log",
        spectre_static_log=logs_dir / "spectre_static.log",
        spectre_dynamic_log=logs_dir / "spectre_dynamic.log",
        ngspice_static_log=logs_dir / "ngspice_static.log",
        ngspice_dynamic_log=logs_dir / "ngspice_dynamic.log",
        veriloga_model=veriloga_dir / "configurable_adc.va",
    )


def archive_veriloga_artifacts(repo_root: Path, output_dir: Path) -> Path:
    """Copy Verilog-A model and simulator testbenches into the output folder."""
    paths = prepare_output_dirs(output_dir)
    sources = [
        repo_root / "veriloga/configurable_adc.va",
        repo_root / "testbench/spectre/adc_include.scs",
        repo_root / "testbench/spectre/static_inl_dnl.scs",
        repo_root / "testbench/spectre/dynamic_spectrum.scs",
        repo_root / "testbench/ngspice/static_inl_dnl.cir",
        repo_root / "testbench/ngspice/dynamic_spectrum.cir",
        repo_root / "testbench/ngspice/adc_behavioral.inc",
    ]
    for source in sources:
        if source.is_file():
            shutil.copy2(source, paths.veriloga_dir / source.name)
    return paths.veriloga_model


def _format_mapping(title: str, values: dict[str, Any]) -> list[str]:
    """Format a section of key/value pairs for a text log."""
    lines = [f"[{title}]", *(f"{key}={value}" for key, value in values.items()), ""]
    return lines


def write_python_simulation_log(
    log_path: Path,
    *,
    test_name: str,
    cfg: AdcConfig,
    noise: AdcNoiseConfig,
    test_params: dict[str, Any],
    results: dict[str, Any],
    veriloga_model: Path | None = None,
) -> Path:
    """Write a human-readable Python simulation log."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        f"# Python simulation log: {test_name}",
        f"Generated: {timestamp}",
        f"Python: {sys.version.split()[0]}",
        "Engine: Python behavioral model (matches veriloga/configurable_adc.va)",
        "",
    ]
    if veriloga_model is not None:
        lines.extend([f"Verilog-A reference: {veriloga_model.name}", ""])

    lines.extend(
        _format_mapping(
            "ADC Config",
            {
                "bits": cfg.bits,
                "vrefp": cfg.vrefp,
                "vrefn": cfg.vrefn,
                "gain": cfg.gain,
                "offset_v": cfg.offset_v,
                "fs_hz": cfg.fs_hz,
            },
        )
    )
    lines.extend(
        _format_mapping(
            "Noise Config",
            {
                "sigma_thermal_v": noise.sigma_thermal_v,
                "jitter_rms_s": noise.jitter_rms_s,
                "nonlinearity_a2": noise.nonlinearity_a2,
                "nonlinearity_a3": noise.nonlinearity_a3,
                "dnl_sigma_lsb": noise.dnl_sigma_lsb,
                "noise_seed": noise.noise_seed,
                "enabled": noise.enabled,
            },
        )
    )
    lines.extend(_format_mapping("Testbench", test_params))
    lines.extend(_format_mapping("Results", results))
    log_path.write_text("\n".join(lines), encoding="utf-8")
    return log_path.resolve()


def run_spectre_testbench(
    *,
    repo_root: Path,
    scs_path: Path,
    output_csv: Path,
    log_path: Path,
    fs_hz: float,
    max_samples: int | None = None,
    cfg: AdcConfig | None = None,
    noise: AdcNoiseConfig | None = None,
    samples_per_code: int | None = None,
    num_samples: int | None = None,
    coherent_bin: int | None = None,
) -> Path:
    """Run a Spectre testbench and capture simulator output to a log file."""
    from adc_model.spectre_engine import run_spectre_testbench as _run

    return _run(
        repo_root=repo_root,
        scs_path=scs_path,
        output_csv=output_csv,
        log_path=log_path,
        fs_hz=fs_hz,
        max_samples=max_samples,
        cfg=cfg,
        noise=noise,
        samples_per_code=samples_per_code,
        num_samples=num_samples,
        coherent_bin=coherent_bin,
    )


def collect_log_files(
    paths: SimulationLogPaths,
    *,
    simulator: str,
) -> tuple[Path, ...]:
    """Return log files that exist for inclusion in the report."""
    candidates = [paths.python_static_log, paths.python_dynamic_log]
    if simulator == "spectre":
        candidates.extend([paths.spectre_static_log, paths.spectre_dynamic_log])
    elif simulator == "ngspice":
        candidates.extend([paths.ngspice_static_log, paths.ngspice_dynamic_log])
    return tuple(path.resolve() for path in candidates if path.is_file())
