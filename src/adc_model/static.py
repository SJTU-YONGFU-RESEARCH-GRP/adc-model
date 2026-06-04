"""Static linearity (INL/DNL) computation and plotting."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from numpy.typing import NDArray

from adc_model.config import AdcConfig
from adc_model.plot_style import (
    LABEL_SIZE,
    LINE_COLORS,
    LINEWIDTH_MAIN,
    LINEWIDTH_SECONDARY,
    TITLE_SIZE,
    apply_rcparams,
    apply_style,
    downsample_stride,
)

# Exclude end codes from reported metrics (quantizer saturation shoulders).
_EDGE_CODE_MARGIN = 1


@dataclass(frozen=True)
class StaticLinearity:
    """INL/DNL results from a ramp capture."""

    codes: NDArray[np.int64]
    dnl_lsb: NDArray[np.float64]
    inl_lsb: NDArray[np.float64]
    max_dnl_lsb: float
    max_inl_lsb: float


def decode_codes(v_code: NDArray[np.float64], cfg: AdcConfig) -> NDArray[np.int64]:
    """Recover integer ADC codes from ``v_code`` bus samples."""
    if cfg.lsb <= 0.0:
        msg = "LSB must be positive."
        raise ValueError(msg)
    return np.rint(v_code / cfg.lsb).astype(np.int64)


def _interior_metrics(dnl: NDArray[np.float64], inl: NDArray[np.float64]) -> tuple[float, float]:
    """Return max |DNL|/|INL| over interior codes, excluding saturation shoulders."""
    if len(dnl) <= 2 * _EDGE_CODE_MARGIN:
        return float(np.max(np.abs(dnl))), float(np.max(np.abs(inl)))
    dnl_interior = dnl[_EDGE_CODE_MARGIN:-_EDGE_CODE_MARGIN]
    inl_interior = inl[_EDGE_CODE_MARGIN:-_EDGE_CODE_MARGIN]
    return float(np.max(np.abs(dnl_interior))), float(np.max(np.abs(inl_interior)))


def compute_inl_dnl_histogram(
    codes: NDArray[np.int64],
    cfg: AdcConfig,
) -> StaticLinearity:
    """Compute INL/DNL from ramp histogram (robust when noise is present)."""
    interior_mask = (codes > 0) & (codes < cfg.max_code)
    if np.count_nonzero(interior_mask) < cfg.max_code:
        msg = "Insufficient interior code hits for histogram INL/DNL analysis."
        raise ValueError(msg)

    counts = np.bincount(codes[interior_mask], minlength=cfg.num_codes).astype(np.float64)
    active = counts[1 : cfg.max_code] > 0
    if np.count_nonzero(active) < 2:
        msg = "Insufficient code hits for histogram INL/DNL analysis."
        raise ValueError(msg)

    expected = float(np.mean(counts[1 : cfg.max_code][active]))
    code_axis = np.arange(1, cfg.max_code, dtype=np.int64)
    dnl = counts[1 : cfg.max_code] / expected - 1.0
    inl = np.cumsum(dnl)
    inl = inl - np.linspace(inl[0], inl[-1], len(inl))
    max_dnl, max_inl = _interior_metrics(dnl, inl)

    return StaticLinearity(
        codes=code_axis,
        dnl_lsb=dnl,
        inl_lsb=inl,
        max_dnl_lsb=max_dnl,
        max_inl_lsb=max_inl,
    )


def compute_inl_dnl(
    vin: NDArray[np.float64],
    codes: NDArray[np.int64],
    cfg: AdcConfig,
    *,
    method: str = "auto",
) -> StaticLinearity:
    """Compute INL/DNL from a monotonic ramp capture.

    Transition voltages are extracted at rising code edges. DNL is computed from
    code-bin widths; INL is the cumulative sum with end-point normalization.

    Args:
        vin: Input voltage sampled once per clock.
        codes: Integer ADC output codes.
        cfg: ADC configuration.
        method: ``auto``, ``transition``, or ``histogram``.

    Returns:
        Static linearity metrics versus code index.
    """
    if method == "histogram":
        return compute_inl_dnl_histogram(codes, cfg)
    if method == "auto":
        # Few monotonic rising edges → noisy/dithered ramp; use histogram DNL.
        unique_transitions = int(np.sum(codes[1:] > codes[:-1]))
        if unique_transitions < cfg.max_code // 2:
            return compute_inl_dnl_histogram(codes, cfg)

    return _compute_inl_dnl_transition(vin, codes, cfg)


def _compute_inl_dnl_transition(
    vin: NDArray[np.float64],
    codes: NDArray[np.int64],
    cfg: AdcConfig,
) -> StaticLinearity:
    max_code = cfg.max_code
    lsb_ideal = cfg.lsb
    num_transitions = max_code + 1

    transitions = np.full(num_transitions, np.nan, dtype=np.float64)
    transitions[0] = cfg.vrefn
    transitions[max_code] = cfg.vrefp

    for idx in range(1, len(codes)):
        if codes[idx] > codes[idx - 1]:
            rising_code = int(codes[idx])
            if 0 < rising_code < max_code:
                transitions[rising_code] = 0.5 * (vin[idx] + vin[idx - 1])

    axis = np.arange(num_transitions, dtype=np.float64)
    known = np.isfinite(transitions)
    if np.count_nonzero(known) < 2:
        msg = "Insufficient code transitions for INL/DNL analysis."
        raise ValueError(msg)
    transitions = np.interp(axis, axis[known], transitions[known])

    widths = np.diff(transitions)
    code_axis = np.arange(1, max_code, dtype=np.int64)
    dnl = widths[1:max_code] / lsb_ideal - 1.0
    inl = np.cumsum(dnl)
    inl = inl - np.linspace(inl[0], inl[-1], len(inl))
    max_dnl, max_inl = _interior_metrics(dnl, inl)

    return StaticLinearity(
        codes=code_axis,
        dnl_lsb=dnl,
        inl_lsb=inl,
        max_dnl_lsb=max_dnl,
        max_inl_lsb=max_inl,
    )


def _data_ylim(values: NDArray[np.float64]) -> tuple[float, float]:
    """Return y-limits that tightly frame plotted data with small padding."""
    vmin = float(np.min(values))
    vmax = float(np.max(values))
    if np.isclose(vmin, vmax):
        pad = max(0.02, abs(vmax) * 0.05, 0.05)
        return vmin - pad, vmax + pad
    pad = max(0.02, 0.05 * (vmax - vmin))
    return vmin - pad, vmax + pad


def plot_inl_dnl(
    result: StaticLinearity,
    cfg: AdcConfig,
    output_path: Path,
    *,
    title: str | None = None,
) -> None:
    """Plot DNL and INL versus code and save as SVG."""
    apply_rcparams()
    fig, axes = plt.subplots(2, 1, figsize=(11, 7.5), sharex=True)

    stride = downsample_stride(len(result.codes))
    x_plot = result.codes[::stride]
    dnl_plot = result.dnl_lsb[::stride]
    inl_plot = result.inl_lsb[::stride]

    dnl_ymin, dnl_ymax = _data_ylim(dnl_plot)
    inl_ymin, inl_ymax = _data_ylim(inl_plot)

    axes[0].plot(
        x_plot,
        dnl_plot,
        color=LINE_COLORS["dnl"],
        linewidth=LINEWIDTH_MAIN,
        marker="s",
        markersize=4,
        markevery=max(stride // 2, 1),
        markerfacecolor="white",
        markeredgewidth=1.0,
        label="DNL",
    )
    axes[0].set_ylabel("DNL (LSB)", fontsize=LABEL_SIZE)
    axes[0].set_ylim(dnl_ymin, dnl_ymax)
    axes[0].set_title(
        title or f"Static linearity ({cfg.bits}-bit ADC)",
        fontsize=TITLE_SIZE,
    )
    axes[0].legend(fontsize=9, loc="upper right")
    apply_style(axes[0])

    axes[1].plot(
        x_plot,
        inl_plot,
        color=LINE_COLORS["inl"],
        linewidth=LINEWIDTH_SECONDARY,
        marker="o",
        markersize=4,
        markevery=max(stride // 2, 1),
        markerfacecolor="white",
        markeredgewidth=1.0,
        label="INL",
    )
    axes[1].set_xlabel("Code", fontsize=LABEL_SIZE)
    axes[1].set_ylabel("INL (LSB)", fontsize=LABEL_SIZE)
    axes[1].set_ylim(inl_ymin, inl_ymax)
    axes[1].legend(fontsize=9, loc="upper right")
    apply_style(axes[1])

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, format="svg")
    plt.close(fig)
