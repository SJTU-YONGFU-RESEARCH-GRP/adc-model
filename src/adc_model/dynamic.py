"""Dynamic FFT metrics and spectrum plotting."""

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
    FIGSIZE,
    LABEL_SIZE,
    LINE_COLORS,
    LINEWIDTH_MAIN,
    TITLE_SIZE,
    apply_rcparams,
    apply_style,
)


@dataclass(frozen=True)
class HarmonicTone:
    """Identified tone in the output spectrum."""

    order: int
    bin_index: int
    freq_hz: float
    magnitude_dbfs: float
    aliased: bool


@dataclass(frozen=True)
class DynamicMetrics:
    """Dynamic performance metrics from a coherent FFT capture."""

    freq_hz: NDArray[np.float64]
    magnitude_dbfs: NDArray[np.float64]
    fin_hz: float
    signal_bin: int
    harmonics: tuple[HarmonicTone, ...]
    sndr_db: float
    sfdr_db: float
    enob_bits: float
    thd_db: float


SPECTRUM_PLOT_FLOOR_DBFS = -120.0
NOISE_FLOOR_MARGIN_DB = 8.0
PEAK_HEADROOM_DB = 10.0


def _estimate_noise_floor_dbfs(
    magnitude_dbfs: NDArray[np.float64],
    harmonics: tuple[HarmonicTone, ...],
    *,
    exclude_bins: int = 3,
) -> float:
    """Estimate the spectrum noise floor from non-tone FFT bins."""
    excluded: set[int] = {0}
    for tone in harmonics:
        for offset in range(-exclude_bins, exclude_bins + 1):
            idx = tone.bin_index + offset
            if 0 <= idx < len(magnitude_dbfs):
                excluded.add(idx)

    noise_values = np.array(
        [
            magnitude_dbfs[idx]
            for idx in range(1, len(magnitude_dbfs))
            if idx not in excluded and np.isfinite(magnitude_dbfs[idx])
        ],
        dtype=np.float64,
    )
    if noise_values.size == 0:
        return SPECTRUM_PLOT_FLOOR_DBFS
    return float(np.percentile(noise_values, 10))


def _spectrum_for_plot(
    freq_hz: NDArray[np.float64],
    magnitude_dbfs: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return spectrum arrays suitable for plotting (skip DC)."""
    return freq_hz[1:], magnitude_dbfs[1:].copy()


def _find_signal_bin(spectrum_power: NDArray[np.float64], coherent_bin: int) -> int:
    """Return FFT bin index for the fundamental tone."""
    search = 3
    start = max(coherent_bin - search, 1)
    end = min(coherent_bin + search, len(spectrum_power) - 1)
    return int(start + np.argmax(spectrum_power[start : end + 1]))


def _folded_harmonic_bin(fundamental_bin: int, order: int, num_samples: int) -> tuple[int, bool] | None:
    """Return the rFFT bin index for harmonic ``order``, with aliasing flag."""
    if order < 1:
        return None

    raw_bin = fundamental_bin * order
    nyquist_bin = num_samples // 2
    if raw_bin <= nyquist_bin and raw_bin < num_samples:
        return raw_bin, False

    alias_bin = num_samples - raw_bin
    if 0 < alias_bin <= nyquist_bin:
        return alias_bin, True

    return None


def _locate_tone_bin(
    spectrum_power: NDArray[np.float64],
    target_bin: int,
    *,
    exclude_bins: int,
) -> int:
    """Refine a tone location by searching around the expected coherent bin."""
    lo = max(target_bin - exclude_bins, 1)
    hi = min(target_bin + exclude_bins, len(spectrum_power) - 1)
    return lo + int(np.argmax(spectrum_power[lo : hi + 1]))


def _identify_harmonics(
    *,
    signal_bin: int,
    num_samples: int,
    fs_hz: float,
    power: NDArray[np.float64],
    magnitude_dbfs: NDArray[np.float64],
    num_harmonics: int,
    exclude_bins: int,
    min_harmonic_dbfs: float,
) -> tuple[HarmonicTone, ...]:
    """Identify the fundamental and its harmonics in the output spectrum."""
    tones: list[HarmonicTone] = []
    fin_hz = signal_bin * fs_hz / num_samples
    fund_mag = float(magnitude_dbfs[signal_bin])
    tones.append(
        HarmonicTone(
            order=1,
            bin_index=signal_bin,
            freq_hz=fin_hz,
            magnitude_dbfs=fund_mag,
            aliased=False,
        )
    )

    for order in range(2, num_harmonics + 2):
        folded = _folded_harmonic_bin(signal_bin, order, num_samples)
        if folded is None:
            continue
        target_bin, aliased = folded
        local_bin = _locate_tone_bin(power, target_bin, exclude_bins=exclude_bins)
        local_mag = float(magnitude_dbfs[local_bin])
        if not np.isfinite(local_mag) or local_mag < min_harmonic_dbfs:
            continue
        tones.append(
            HarmonicTone(
                order=order,
                bin_index=local_bin,
                freq_hz=local_bin * fs_hz / num_samples,
                magnitude_dbfs=local_mag,
                aliased=aliased,
            )
        )

    return tuple(tones)


def compute_dynamic_metrics(
    codes: NDArray[np.int64],
    cfg: AdcConfig,
    *,
    fin_hz: float,
    num_harmonics: int = 5,
    exclude_bins: int = 2,
    min_harmonic_dbfs: float = -110.0,
) -> DynamicMetrics:
    """Compute SNDR, SFDR, ENOB, and THD from output codes."""
    num_samples = len(codes)
    if num_samples < 16:
        msg = "Need at least 16 samples for FFT analysis."
        raise ValueError(msg)

    # Coherent FFT: integer bin avoids spectral leakage for single-tone SNDR/THD.
    coherent_bin = int(round(fin_hz * num_samples / cfg.fs_hz))
    if coherent_bin <= 0 or coherent_bin >= num_samples // 2:
        msg = f"Input tone is not coherently sampled: bin={coherent_bin}"
        raise ValueError(msg)

    centered = codes.astype(np.float64) - np.mean(codes)
    spectrum = np.fft.rfft(centered)
    power = np.abs(spectrum) ** 2
    # One-sided spectrum: double interior bins (DC/Nyquist unchanged).
    power[1:-1] *= 2.0

    # dBFS reference: sine peak at max_code/2 (full-scale amplitude).
    full_scale_power = (cfg.max_code / 2.0) ** 2 / 2.0
    magnitude_dbfs = 10.0 * np.log10(np.maximum(power / full_scale_power, 1.0e-30))
    if power[0] <= 1.0e-30:
        magnitude_dbfs[0] = np.nan
    freq_hz = np.fft.rfftfreq(num_samples, d=1.0 / cfg.fs_hz)

    signal_bin = _find_signal_bin(power, coherent_bin)
    signal_power = power[signal_bin]
    harmonics = _identify_harmonics(
        signal_bin=signal_bin,
        num_samples=num_samples,
        fs_hz=cfg.fs_hz,
        power=power,
        magnitude_dbfs=magnitude_dbfs,
        num_harmonics=num_harmonics,
        exclude_bins=exclude_bins,
        min_harmonic_dbfs=min_harmonic_dbfs,
    )

    harmonic_bins = [tone.bin_index for tone in harmonics if tone.order > 1]
    harmonic_power = float(
        sum(power[bin_idx] for bin_idx in harmonic_bins),
    )

    # SNDR noise floor: all bins except DC, signal, and guarded harmonic skirts.
    excluded = {0, signal_bin}
    for harmonic_bin in harmonic_bins:
        for offset in range(-exclude_bins, exclude_bins + 1):
            excluded.add(int(np.clip(harmonic_bin + offset, 0, len(power) - 1)))

    noise_bins = np.array([idx for idx in range(1, len(power)) if idx not in excluded])
    noise_power = float(np.sum(power[noise_bins]))

    sndr_db = 10.0 * np.log10(signal_power / max(noise_power, 1.0e-30))
    thd_db = 10.0 * np.log10(max(harmonic_power, 1.0e-30) / signal_power)

    spur_power = 0.0
    for idx in range(1, len(power)):
        if idx in excluded:
            continue
        spur_power = max(spur_power, power[idx])
    sfdr_db = 10.0 * np.log10(signal_power / max(spur_power, 1.0e-30))
    enob_bits = (sndr_db - 1.76) / 6.02

    return DynamicMetrics(
        freq_hz=freq_hz,
        magnitude_dbfs=magnitude_dbfs,
        fin_hz=fin_hz,
        signal_bin=signal_bin,
        harmonics=harmonics,
        sndr_db=float(sndr_db),
        sfdr_db=float(sfdr_db),
        enob_bits=float(enob_bits),
        thd_db=float(-thd_db),
    )


def plot_spectrum(
    result: DynamicMetrics,
    cfg: AdcConfig,
    output_path: Path,
    *,
    title: str | None = None,
    nyquist_only: bool = True,
    annotate_harmonics: bool = True,
) -> None:
    """Plot the output spectrum and annotate dynamic metrics."""
    apply_rcparams()
    fig, ax = plt.subplots(figsize=FIGSIZE)

    freq, mag = _spectrum_for_plot(result.freq_hz, result.magnitude_dbfs)
    if nyquist_only:
        mask = freq <= cfg.fs_hz / 2.0 + 1.0
        freq = freq[mask]
        mag = mag[mask]

    ax.plot(
        freq / 1.0e6,
        mag,
        color=LINE_COLORS["spectrum"],
        linewidth=LINEWIDTH_MAIN,
        label="Spectrum",
    )

    noise_floor = _estimate_noise_floor_dbfs(result.magnitude_dbfs, result.harmonics)
    tone_peaks = [tone.magnitude_dbfs for tone in result.harmonics if np.isfinite(tone.magnitude_dbfs)]
    peak_dbfs = float(np.nanmax(mag)) if mag.size else noise_floor
    if tone_peaks:
        peak_dbfs = max(peak_dbfs, float(np.max(tone_peaks)))
    ymin = noise_floor - NOISE_FLOOR_MARGIN_DB
    ymax = peak_dbfs + PEAK_HEADROOM_DB
    ax.set_ylim(ymin, ymax)

    if annotate_harmonics:
        label_offsets = (12, 12, 10, 8, 6, 4)
        for idx, tone in enumerate(result.harmonics):
            freq_mhz = tone.freq_hz / 1.0e6
            if nyquist_only and tone.freq_hz > cfg.fs_hz / 2.0 + 1.0:
                continue

            if tone.order == 1:
                color = LINE_COLORS["inl"]
                marker = "^"
                label = "Fin"
                linestyle = "--"
            else:
                color = LINE_COLORS["thd"]
                marker = "o"
                suffix = "*" if tone.aliased else ""
                label = f"H{tone.order}{suffix}"
                linestyle = ":"

            ax.axvline(freq_mhz, color=color, linewidth=1.5, linestyle=linestyle, alpha=0.85)
            ax.scatter(
                freq_mhz,
                tone.magnitude_dbfs,
                s=70,
                marker=marker,
                facecolors="white" if tone.order == 1 else color,
                edgecolors=color,
                linewidths=1.5,
                zorder=5,
            )
            y_offset = label_offsets[min(idx, len(label_offsets) - 1)]
            ax.annotate(
                label,
                xy=(freq_mhz, tone.magnitude_dbfs),
                xytext=(0, y_offset),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=9,
                color=color,
                bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "none", "pad": 1.5},
            )

    ax.set_xlabel("Frequency (MHz)", fontsize=LABEL_SIZE)
    ax.set_ylabel("Magnitude (dBFS)", fontsize=LABEL_SIZE)
    ax.set_title(
        title or f"Dynamic spectrum ({cfg.bits}-bit ADC)",
        fontsize=TITLE_SIZE,
    )
    apply_style(ax)
    if annotate_harmonics and result.harmonics:
        ax.legend(fontsize=8, loc="upper right")

    annotation = (
        f"Fin = {result.fin_hz / 1.0e6:.4f} MHz\n"
        f"SNDR = {result.sndr_db:.2f} dB\n"
        f"SFDR = {result.sfdr_db:.2f} dB\n"
        f"THD  = {result.thd_db:.2f} dB\n"
        f"ENOB = {result.enob_bits:.2f} bits"
    )
    ax.text(
        0.02,
        0.98,
        annotation,
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=10,
        bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "none"},
    )

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, format="svg")
    plt.close(fig)
