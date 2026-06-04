"""Utilities for comparing static ramp captures across simulation engines.

**Transitions** count S&H updates (``code[i] != code[i-1]``), which can exceed the
number of unique codes when noise dithers. **Expected hits/code** is the nominal
histogram mean for a uniform ramp: ``num_samples / max_code`` interior codes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from adc_model.config import AdcConfig, AdcNoiseConfig
from adc_model.io import read_waveform_csv
from adc_model.static import compute_inl_dnl, decode_codes


@dataclass(frozen=True)
class StaticEngineStats:
    """Summary statistics for one static ramp capture."""

    engine: str
    num_samples: int
    transitions: int
    count_min: float
    count_max: float
    count_mean: float
    count_std: float
    max_dnl_lsb: float
    max_inl_lsb: float
    inl_dnl_method: str


def resolve_inl_dnl_method(noise: AdcNoiseConfig, method: str) -> str:
    """Return the INL/DNL method used by ``run_static.py`` for the given noise profile."""
    if method != "auto":
        return method
    # Noisy ramps: histogram; ideal: transition voltages (``auto`` in compute_inl_dnl).
    return "histogram" if noise.enabled else "auto"


def expected_hits_per_code(
    cfg: AdcConfig,
    *,
    samples_per_code: int,
    noise: AdcNoiseConfig,
) -> float:
    """Return the nominal histogram hits per interior code for a uniform ramp.

    Uses the same effective ``samples_per_code`` (min 16 with noise) as
    :func:`adc_model.model.simulate_static`. Formula:
      ``expected = (num_codes * samples_per_code) / max_code`` hits per code 1..N-1.
    """
    effective_spc = samples_per_code
    if noise.enabled and effective_spc < 16:
        effective_spc = 16
    num_samples = cfg.num_codes * effective_spc
    return num_samples / cfg.max_code


def code_hit_stats(codes: NDArray[np.int64], cfg: AdcConfig) -> tuple[float, float, float, float]:
    """Return min, max, mean, and std of interior code hit counts."""
    interior = codes[(codes > 0) & (codes < cfg.max_code)]
    counts = np.bincount(interior, minlength=cfg.num_codes)[1 : cfg.max_code]
    active = counts > 0
    if np.count_nonzero(active) < 2:
        return float("nan"), float("nan"), float("nan"), float("nan")
    active_counts = counts[active].astype(np.float64)
    return (
        float(np.min(active_counts)),
        float(np.max(active_counts)),
        float(np.mean(active_counts)),
        float(np.std(active_counts)),
    )


def analyze_static_waveform(
    engine: str,
    waveform_path: Path,
    cfg: AdcConfig,
    *,
    inl_dnl_method: str,
) -> StaticEngineStats:
    """Load a static CSV and compute ramp / INL/DNL summary metrics.

    Args:
        engine: Label for the comparison table (e.g. ``python``, ``ngspice``).
        waveform_path: Exported static waveform CSV.
        inl_dnl_method: ``histogram``, ``transition``, or ``auto`` (see :mod:`static`).

    Returns:
        Summary including transition count, hit-count spread, and max |INL|/|DNL| (LSB).
    """
    if not waveform_path.is_file():
        msg = f"Waveform not found for {engine}: {waveform_path}"
        raise FileNotFoundError(msg)

    data = read_waveform_csv(waveform_path)
    codes = decode_codes(data["v_code"], cfg)
    # Transition = any change in held output between consecutive samples (S&H edges).
    transitions = int(np.sum(codes[1:] != codes[:-1]))
    count_min, count_max, count_mean, count_std = code_hit_stats(codes, cfg)
    linearity = compute_inl_dnl(data["vin"], codes, cfg, method=inl_dnl_method)

    return StaticEngineStats(
        engine=engine,
        num_samples=len(codes),
        transitions=transitions,
        count_min=count_min,
        count_max=count_max,
        count_mean=count_mean,
        count_std=count_std,
        max_dnl_lsb=linearity.max_dnl_lsb,
        max_inl_lsb=linearity.max_inl_lsb,
        inl_dnl_method=inl_dnl_method,
    )


def format_static_comparison_table(
    rows: list[StaticEngineStats],
    *,
    expected_hits: float,
) -> str:
    """Return a human-readable side-by-side comparison table."""
    lines = [
        f"{'Engine':<10} {'Samples':>8} {'Transitions':>12} "
        f"{'Hits min':>9} {'Hits max':>9} {'Hits mean':>10} {'Hits std':>9} "
        f"{'Max |DNL|':>10} {'Max |INL|':>10}",
        "-" * 96,
    ]
    for row in rows:
        lines.append(
            f"{row.engine:<10} {row.num_samples:>8} {row.transitions:>12} "
            f"{row.count_min:>9.0f} {row.count_max:>9.0f} {row.count_mean:>10.2f} "
            f"{row.count_std:>9.2f} {row.max_dnl_lsb:>10.3f} {row.max_inl_lsb:>10.3f}"
        )
    lines.append("")
    lines.append(f"Expected hits/code (uniform ramp): {expected_hits:.1f}")
    if rows:
        lines.append(f"INL/DNL method: {rows[0].inl_dnl_method}")
    return "\n".join(lines)
