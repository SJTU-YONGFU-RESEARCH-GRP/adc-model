"""Behavioral ADC model matching ``veriloga/configurable_adc.va``.

Static ramps use two sampling policies:
  - **Noisy / DNL**: one conversion per rising clock edge at ``@(cross(clk))``
    (``samples_per_code`` dwell clocks per code for histogram depth).
  - **Ideal**: quantize the effective input every clock; hold ``v_code`` until the
    integer bin changes (Verilog-A sample-and-hold, not one update per edge).

Dynamic captures always quantize on rising clock edges (or uniform ``1/fs`` grid),
then expand sparse edge decisions to a full-rate S&H ``v_code`` bus for CSV/plots.

Ramp stimulus spans ``[vrefn + 0.5·LSB, vrefp - 0.5·LSB]`` so each interior code
is visited at its ideal transition center without saturation pile-up at the rails.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from adc_model.config import AdcConfig, AdcNoiseConfig
from adc_model.io import (
    adc_capture_edge_indices,
    clock_pulse_waveform,
    static_capture_edge_indices,
)
from adc_model.noise import (
    apply_analog_front_end,
    apply_analog_front_end_at_edges,
    build_dnl_profile,
    quantize_front_end,
)


def quantize_array(
    vin: NDArray[np.float64],
    cfg: AdcConfig,
    noise: AdcNoiseConfig | None = None,
    *,
    dt: float | None = None,
    rng: np.random.Generator | None = None,
    dnl_profile: NDArray[np.float64] | None = None,
) -> NDArray[np.int64]:
    """Quantize an array of analog samples with optional noise.

    When noise is disabled, applies only gain/offset then
    ``floor((v_front - vrefn) / (vrefp - vrefn) * max_code + 0.5)`` (V → code).
    Otherwise runs the full front-end chain in :mod:`adc_model.noise` at spacing
    ``dt`` (s), default ``1/fs_hz``.
    """
    noise_cfg = noise or AdcNoiseConfig()
    sample_dt = dt if dt is not None else 1.0 / cfg.fs_hz
    generator = rng if rng is not None else np.random.default_rng(noise_cfg.noise_seed)
    profile = dnl_profile
    if profile is None and noise_cfg.dnl_sigma_lsb > 0.0:
        profile = build_dnl_profile(cfg, noise_cfg)

    if noise_cfg.enabled or profile is not None:
        v_front = apply_analog_front_end(
            vin,
            cfg,
            noise_cfg,
            dt=sample_dt,
            rng=generator,
            dnl_profile=profile,
        )
        return quantize_front_end(v_front, cfg)

    v_eff = cfg.gain * vin + cfg.offset_v
    return quantize_front_end(v_eff, cfg)


def quantize_sample(
    vin: float,
    cfg: AdcConfig,
    noise: AdcNoiseConfig | None = None,
) -> int:
    """Quantize one analog sample using the Verilog-A transfer function."""
    return int(quantize_array(np.array([vin], dtype=np.float64), cfg, noise=noise)[0])


def code_to_v_code(code: int, cfg: AdcConfig) -> float:
    """Convert an integer code to the Verilog-A ``v_code`` output voltage."""
    return code * cfg.lsb


def _simulate_static_ideal_codes(
    vin: NDArray[np.float64],
    cfg: AdcConfig,
) -> NDArray[np.int64]:
    """Quantize an ideal static ramp with Verilog-A-style sample-and-hold.

    At every time index the comparator sees ``v_eff = gain·vin + offset_v`` (V),
    but the held output code updates only when that instantaneous bin differs from
    the previous held value (matches ``v_code`` in ideal VA static mode).
    """
    v_eff = cfg.gain * vin + cfg.offset_v
    # Comparator decision at each clock instant (before S&H).
    codes_at_clk = quantize_front_end(v_eff, cfg)

    # Held output only changes when the instantaneous bin changes (not every clock).
    codes = np.empty(len(vin), dtype=np.int64)
    code_int = int(codes_at_clk[0])
    codes[0] = code_int
    for idx in range(1, len(vin)):
        new_code = int(codes_at_clk[idx])
        if new_code != code_int:
            code_int = new_code
        codes[idx] = code_int
    return codes


def _fill_sample_hold_codes(
    codes_at_edges: NDArray[np.int64],
    edge_idx: NDArray[np.int64],
    num_samples: int,
) -> NDArray[np.int64]:
    """Expand per-edge codes to a sample-and-hold waveform (matches ``v_code``).

    Args:
        codes_at_edges: Integer code decided at each capture index.
        edge_idx: Sample indices where conversions occur (rising ``clk`` or ``n/fs``).
        num_samples: Length of the full simulation time grid.

    Returns:
        Held codes on the dense grid; constant between successive ``edge_idx`` entries.
    """
    codes = np.zeros(num_samples, dtype=np.int64)
    if edge_idx[0] > 0:
        codes[: edge_idx[0]] = 0
    for k, start in enumerate(edge_idx):
        end = int(edge_idx[k + 1]) if k + 1 < len(edge_idx) else num_samples
        codes[start:end] = codes_at_edges[k]
    return codes


def simulate_static(
    cfg: AdcConfig,
    samples_per_code: int = 4,
    noise: AdcNoiseConfig | None = None,
) -> dict[str, NDArray[np.float64]]:
    """Simulate a slow ramp capture for INL/DNL analysis.

    Args:
        cfg: ADC resolution, references, and sample rate ``fs_hz`` (Hz).
        samples_per_code: Clock cycles spent near each code (histogram depth).
            Raised to at least 16 when noise is enabled so dithered codes average out.
        noise: Optional input-referred noise; when enabled, samples only on clock edges.

    Returns:
        Waveform dict with keys ``time`` (s), ``vin``/``v_code`` (V), ``clk`` (0/1),
        and ``code`` (integer level as float for CSV).
    """
    noise_cfg = noise or AdcNoiseConfig()
    # Deeper dwell reduces histogram variance when thermal noise dithers codes.
    if noise_cfg.enabled and samples_per_code < 16:
        samples_per_code = 16

    num_samples = cfg.num_codes * samples_per_code
    dt = 1.0 / cfg.fs_hz
    time = np.arange(num_samples, dtype=np.float64) * dt

    margin = 0.5 * cfg.lsb  # V; half-LSB inset from rails
    # Ramp between code centers so each interior bin gets ~equal hit count.
    vin = np.linspace(cfg.vrefn + margin, cfg.vrefp - margin, num_samples)
    # Clock period 1/fs (matches Spectre ``vsource`` pulse).
    clk = clock_pulse_waveform(time, cfg.fs_hz)
    rng = np.random.default_rng(noise_cfg.noise_seed)
    dnl_profile = build_dnl_profile(cfg, noise_cfg) if noise_cfg.dnl_sigma_lsb > 0.0 else None

    if noise_cfg.enabled or dnl_profile is not None:
        # One conversion per clock edge (matches Verilog-A / Spectre / dynamic capture).
        edge_idx = static_capture_edge_indices(
            num_samples,
            clk,
            samples_per_code=samples_per_code,
            time=time,
            fs_hz=cfg.fs_hz,
        )
        v_front = apply_analog_front_end_at_edges(
            vin,
            edge_idx,
            cfg,
            noise_cfg,
            dt=dt,
            rng=rng,
            dnl_profile=dnl_profile,
        )
        codes_at_edges = quantize_front_end(v_front, cfg)
        codes = _fill_sample_hold_codes(codes_at_edges, edge_idx, num_samples)
    else:
        # Ideal: sample every clock; update held code when the bin changes (matches VA).
        codes = _simulate_static_ideal_codes(vin, cfg)
    v_code = codes.astype(np.float64) * cfg.lsb

    return {
        "time": time,
        "vin": vin,
        "clk": clk,
        "v_code": v_code,
        "code": codes.astype(np.float64),
    }


def simulate_dynamic(
    cfg: AdcConfig,
    *,
    num_samples: int = 8192,
    fin_hz: float | None = None,
    amplitude: float | None = None,
    coherent_bin: int | None = None,
    noise: AdcNoiseConfig | None = None,
) -> dict[str, NDArray[np.float64]]:
    """Simulate a coherent sine capture for FFT analysis.

    The input tone is ``vin = Vcm + A·sin(2π·fin·t)`` with default
    ``A = 0.95·(vrefp - vrefn)/2`` (V). When ``fin_hz`` is omitted,
    ``fin_hz = coherent_bin · fs_hz / num_samples`` so the tone lands on an FFT bin
    (integer ``coherent_bin`` in ``(0, num_samples/2)``).

    Args:
        num_samples: FFT record length (one decision per ``1/fs`` period).
        fin_hz: Input frequency (Hz); mutually exclusive with ``coherent_bin``.
        amplitude: Peak sine amplitude (V).
        coherent_bin: Coherent FFT bin index when ``fin_hz`` is not given.

    Returns:
        Same waveform keys as :func:`simulate_static`, plus ``fin_hz`` (Hz).
    """
    noise_cfg = noise or AdcNoiseConfig()
    dt = 1.0 / cfg.fs_hz
    time = np.arange(num_samples, dtype=np.float64) * dt

    if fin_hz is None:
        bin_idx = coherent_bin if coherent_bin is not None else 997
        if bin_idx <= 0 or bin_idx >= num_samples // 2:
            msg = f"coherent_bin must be in (0, {num_samples // 2}), got {bin_idx}"
            raise ValueError(msg)
        fin_hz = bin_idx * cfg.fs_hz / num_samples

    if amplitude is None:
        amplitude = 0.95 * (cfg.vrefp - cfg.vrefn) / 2.0

    mid = 0.5 * (cfg.vrefp + cfg.vrefn)
    vin = mid + amplitude * np.sin(2.0 * np.pi * fin_hz * time)
    clk = clock_pulse_waveform(time, cfg.fs_hz)
    # One FFT sample per clock period (uniform grid uses index 0..N-1).
    edge_idx = adc_capture_edge_indices(time, cfg.fs_hz, clk)
    rng = np.random.default_rng(noise_cfg.noise_seed)
    dnl_profile = build_dnl_profile(cfg, noise_cfg) if noise_cfg.dnl_sigma_lsb > 0.0 else None

    if noise_cfg.enabled or dnl_profile is not None:
        v_front = apply_analog_front_end_at_edges(
            vin,
            edge_idx,
            cfg,
            noise_cfg,
            dt=dt,
            rng=rng,
            dnl_profile=dnl_profile,
        )
        codes_at_edges = quantize_front_end(v_front, cfg)
    else:
        v_eff = cfg.gain * vin[edge_idx] + cfg.offset_v
        codes_at_edges = quantize_front_end(v_eff, cfg)

    # Expand sparse edge decisions to a full-rate S&H bus for CSV/plots.
    codes = _fill_sample_hold_codes(codes_at_edges, edge_idx, num_samples)
    v_code = codes.astype(np.float64) * cfg.lsb

    return {
        "time": time,
        "vin": vin,
        "clk": clk,
        "v_code": v_code,
        "code": codes.astype(np.float64),
        "fin_hz": np.array([fin_hz], dtype=np.float64),
    }
