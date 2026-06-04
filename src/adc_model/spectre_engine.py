"""Cadence Spectre testbench runner and nutascii waveform export."""

from __future__ import annotations

import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from adc_model.config import AdcConfig, AdcNoiseConfig
from adc_model.io import prepare_edge_aligned_waveform, write_waveform_csv

_PARAMETER_LINE = re.compile(r"^parameters\s+(\w+)=(.*)$", re.MULTILINE)
_ADC_INCLUDE = re.compile(
    r'include\s+"\./testbench/spectre/adc_include\.scs"\s*',
    re.IGNORECASE,
)

# Match Python / ngspice static capture depth when noise is enabled.
_MIN_SAMPLES_PER_CODE_WITH_NOISE = 16

# Spectre nutascii may split ``v_code`` onto a second line when the index row is short.


def _absolutize_spectre_includes(text: str, repo_root: Path) -> str:
    """Replace repo-relative ``include`` with an absolute ``ahdl_include`` path.

    Rendered netlists run from ``<output>/logs/``; relative paths would break VA load.
    """
    va_path = (repo_root / "veriloga/configurable_adc.va").resolve()
    return _ADC_INCLUDE.sub(f'ahdl_include "{va_path}"\n', text)


def _spectre_artifact_paths(directory: Path, netlist_stem: str) -> list[Path]:
    """Return Spectre AHDL cache / log paths created for a netlist stem."""
    return [
        directory / f"{netlist_stem}.ahdlSimDB",
        directory / "status",
    ]


def cleanup_spectre_artifacts(
    directory: Path,
    netlist_stem: str,
    *,
    remove_ahdl_cache: bool = True,
) -> None:
    """Remove Spectre run debris under ``directory`` (no-op if missing).

    Args:
        directory: Folder where Spectre was launched.
        netlist_stem: Base name of the ``.scs`` file (e.g. ``static_inl_dnl``).
        remove_ahdl_cache: When False, keep ``.ahdlSimDB`` for faster re-runs.
    """
    for path in _spectre_artifact_paths(directory, netlist_stem):
        if not path.exists():
            continue
        if path.name.endswith(".ahdlSimDB") and not remove_ahdl_cache:
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def _effective_samples_per_code(samples_per_code: int, noise: AdcNoiseConfig) -> int:
    """Return static ramp depth aligned with ``simulate_static`` / ngspice."""
    if noise.enabled and samples_per_code < _MIN_SAMPLES_PER_CODE_WITH_NOISE:
        return _MIN_SAMPLES_PER_CODE_WITH_NOISE
    return samples_per_code

def read_spectre_nutascii(path: Path) -> dict[str, NDArray[np.float64]]:
    """Read a Spectre nutascii transient raw file.

    Nutascii layout:
      - Header ``Variables:`` lists ``index name unit`` triplets per signal.
      - ``Values:`` section: one row per time point with leading index + scalars;
        when the row is shorter than the variable count, the next line is a
        continuation (commonly carries ``v_code`` alone).

    Units follow Spectre export (typically ``time`` in s, ``vin``/``v_code`` in V).

    Args:
        path: Nutascii raw file produced by ``spectre -format nutascii -raw``.

    Returns:
        Waveform arrays keyed by signal name (``time``, ``vin``, ``clk``, ``v_code``).
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    try:
        values_idx = lines.index("Values:")
    except ValueError as exc:
        msg = f"No Values section found in Spectre raw file: {path}"
        raise ValueError(msg) from exc

    var_names = _parse_variable_names(lines[:values_idx])
    if not var_names:
        msg = f"No variables found in Spectre raw file: {path}"
        raise ValueError(msg)

    columns: dict[str, list[float]] = {name: [] for name in var_names}
    data_lines = lines[values_idx + 1 :]
    line_idx = 0
    while line_idx < len(data_lines):
        row = _split_numeric_row(data_lines[line_idx])
        line_idx += 1
        if len(row) < 2:
            continue
        values = row[1:]
        # Continuation line carries trailing signals (often ``v_code`` only).
        if len(values) < len(var_names) and line_idx < len(data_lines):
            values.extend(_split_numeric_row(data_lines[line_idx]))
            line_idx += 1
        if len(values) < len(var_names):
            msg = (
                f"Expected {len(var_names)} samples per point in {path}, "
                f"got {len(values)}."
            )
            raise ValueError(msg)
        for name, value in zip(var_names, values[: len(var_names)], strict=True):
            columns[name].append(value)

    return {name: np.asarray(values, dtype=np.float64) for name, values in columns.items()}


def _parse_variable_names(header_lines: list[str]) -> list[str]:
    """Extract signal names from the nutascii ``Variables:`` header."""
    names: list[str] = []
    in_variables = False
    for line in header_lines:
        if line.startswith("Variables:"):
            in_variables = True
            names.extend(_variable_names_from_line(line))
            continue
        if not in_variables:
            continue
        if line.startswith("Values:"):
            break
        names.extend(_variable_names_from_line(line))
    return names


def _variable_names_from_line(line: str) -> list[str]:
    """Parse ``index name unit`` triplets from a nutascii Variables row."""
    text = line.split("Variables:", 1)[-1]
    parts = [part.strip() for part in text.split("\t") if part.strip()]
    names: list[str] = []
    idx = 0
    while idx < len(parts):
        if parts[idx].isdigit() and idx + 1 < len(parts):
            names.append(parts[idx + 1])
            idx += 2
            while idx < len(parts) and not parts[idx].isdigit():
                idx += 1
        else:
            idx += 1
    return names


def _split_numeric_row(line: str) -> list[float]:
    """Return floats from a whitespace- or tab-separated nutascii row."""
    tokens = [token for token in re.split(r"[\t ]+", line.strip()) if token]
    return [float(token) for token in tokens]


def _spectre_parameter_value(name: str, value: float | int) -> str:
    """Format a numeric value for a Spectre ``parameters`` assignment."""
    if isinstance(value, int):
        return str(value)
    if value == 0.0:
        return "0.0"
    return f"{value:.12g}"


def render_spectre_netlist(
    template_path: Path,
    *,
    cfg: AdcConfig,
    noise: AdcNoiseConfig,
    repo_root: Path | None = None,
    samples_per_code: int | None = None,
    num_samples: int | None = None,
    coherent_bin: int | None = None,
) -> str:
    """Render a Spectre testbench with CLI ADC/noise settings.

    Args:
        template_path: Source ``.scs`` file under ``testbench/spectre/``.
        cfg: ADC configuration.
        noise: Noise / nonlinearity configuration.
        samples_per_code: Static capture depth override.
        num_samples: Dynamic FFT length override.
        coherent_bin: Coherent FFT bin override.
        repo_root: When set, rewrite the Verilog-A include to an absolute path so
            Spectre can run outside the repository root.

    Returns:
        Rendered netlist text.
    """
    overrides: dict[str, str] = {
        "bits": _spectre_parameter_value("bits", cfg.bits),
        "vrefp": _spectre_parameter_value("vrefp", cfg.vrefp),
        "vrefn": _spectre_parameter_value("vrefn", cfg.vrefn),
        "gain": _spectre_parameter_value("gain", cfg.gain),
        "offset_v": _spectre_parameter_value("offset_v", cfg.offset_v),
        "fs": _spectre_parameter_value("fs", cfg.fs_hz),
        "sigma_thermal": _spectre_parameter_value("sigma_thermal", noise.sigma_thermal_v),
        "jitter_rms": _spectre_parameter_value("jitter_rms", noise.jitter_rms_s),
        "nonlinearity_a2": _spectre_parameter_value("nonlinearity_a2", noise.nonlinearity_a2),
        "nonlinearity_a3": _spectre_parameter_value("nonlinearity_a3", noise.nonlinearity_a3),
        "dnl_sigma_lsb": _spectre_parameter_value("dnl_sigma_lsb", noise.dnl_sigma_lsb),
        "noise_seed": _spectre_parameter_value("noise_seed", noise.noise_seed),
    }
    if samples_per_code is not None:
        effective_spc = _effective_samples_per_code(samples_per_code, noise)
        overrides["samples_per_code"] = _spectre_parameter_value(
            "samples_per_code",
            effective_spc,
        )
        if template_path.stem == "static_inl_dnl":
            overrides["num_samples"] = _spectre_parameter_value(
                "num_samples",
                cfg.num_codes * effective_spc,
            )
    if num_samples is not None:
        overrides["num_samples"] = _spectre_parameter_value("num_samples", num_samples)
    if coherent_bin is not None:
        overrides["coherent_bin"] = _spectre_parameter_value("coherent_bin", coherent_bin)

    text = template_path.read_text(encoding="utf-8")

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in overrides:
            return f"parameters {name}={overrides[name]}"
        return match.group(0)

    text = _PARAMETER_LINE.sub(_replace, text)
    if repo_root is not None:
        text = _absolutize_spectre_includes(text, repo_root)
    return text


def prepare_spectre_waveform(
    waveform: dict[str, NDArray[np.float64]],
    fs_hz: float,
    *,
    max_samples: int | None = None,
) -> dict[str, NDArray[np.float64]]:
    """Downsample dense Spectre transient output to one ADC sample per clock edge.

    Spectre ``maxstep`` is often finer than ``1/fs``; analysis needs one row per
    ADC clock. Delegates to :func:`adc_model.io.prepare_edge_aligned_waveform`, which
    picks ``rising_edge(clk) + 1`` on dense grids (``v_code`` lag) or passes through
    when ``median(dt) ≈ 1/fs``.

    Args:
        waveform: Raw nutascii dict (dense transient).
        fs_hz: ADC sample rate (Hz).
        max_samples: Optional cap after downsampling.
    """
    return prepare_edge_aligned_waveform(
        waveform,
        fs_hz,
        max_samples=max_samples,
    )


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
    cleanup_ahdl_cache: bool = False,
) -> Path:
    """Run a Spectre testbench, export nutascii raw, and write analysis CSV.

    Standalone Spectre does not support the ``+export`` CLI flag; waveforms are
    captured with ``-format nutascii -raw`` and converted to CSV in Python.

    Spectre writes ``<netlist>.ahdlSimDB/`` (Verilog-A compile cache) and a
    ``status`` log in its working directory. Runs use ``log_path.parent`` so
    those files land under the output tree (e.g. ``outputs/.../logs/``), not the
    repo root. Legacy debris in ``repo_root`` is removed before each run.

    Args:
        repo_root: Repository root (for Verilog-A and template paths).
        scs_path: Spectre testbench ``.scs`` path (template or rendered).
        output_csv: Destination waveform CSV for analysis scripts.
        log_path: Simulator log path.
        fs_hz: ADC sample rate used to resample transient results.
        max_samples: Optional sample cap after resampling.
        cfg: ADC settings for rendered netlists (optional).
        noise: Noise settings for rendered netlists (optional).
        samples_per_code: Static test override when rendering.
        num_samples: Dynamic test override when rendering.
        coherent_bin: Dynamic test override when rendering.
        cleanup_ahdl_cache: Delete ``.ahdlSimDB`` under the run directory after
            a successful simulation (kept by default for faster re-runs).

    Returns:
        Resolved simulator log path.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    run_dir = log_path.parent.resolve()
    netlist_stem = scs_path.stem
    # Drop legacy repo-root ``status`` / ``*.ahdlSimDB`` from manual CLI runs.
    cleanup_spectre_artifacts(repo_root.resolve(), netlist_stem)

    run_scs_path = scs_path
    if cfg is not None and noise is not None:
        rendered_dir = run_dir / "netlists"
        rendered_dir.mkdir(parents=True, exist_ok=True)
        run_scs_path = rendered_dir / scs_path.name
        run_scs_path.write_text(
            render_spectre_netlist(
                scs_path,
                cfg=cfg,
                noise=noise,
                repo_root=repo_root,
                samples_per_code=samples_per_code,
                num_samples=num_samples,
                coherent_bin=coherent_bin,
            ),
            encoding="utf-8",
        )
    raw_path = run_dir / f"{netlist_stem}.nutascii"
    cmd = [
        "spectre",
        str(run_scs_path.resolve()),
        "-format",
        "nutascii",
        "-raw",
        str(raw_path.resolve()),
    ]
    header = [
        f"# Spectre simulation log: {scs_path.name}",
        f"Generated: {datetime.now(tz=UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"Spectre run directory: {run_dir}",
        f"Command: {' '.join(cmd)}",
        f"Raw output: {raw_path.resolve()}",
        "",
    ]
    with log_path.open("w", encoding="utf-8") as log_file:
        log_file.write("\n".join(header))
        log_file.flush()
        subprocess.run(
            cmd,
            check=True,
            cwd=run_dir,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
    if cleanup_ahdl_cache:
        cleanup_spectre_artifacts(run_dir, netlist_stem, remove_ahdl_cache=True)
    # Dense transient → one row per ADC clock for analysis scripts.
    waveform = prepare_spectre_waveform(
        read_spectre_nutascii(raw_path),
        fs_hz,
        max_samples=max_samples,
    )
    write_waveform_csv(output_csv, waveform)
    return log_path.resolve()
