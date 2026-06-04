"""Behavioral ADC model matching ``veriloga/configurable_adc.va``.

Static ramps use two sampling policies:
  - Noisy: one conversion per code dwell (``samples_per_code`` clocks).
  - Ideal: quantize every clock; hold ``v_code`` until the bin changes (VA S&H).
Dynamic captures always quantize on rising clock edges, then expand to S&H.
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
    """Quantize an array of analog samples with optional noise."""
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
    """Quantize an ideal static ramp with Verilog-A-style sample-and-hold."""
    v_eff = cfg.gain * vin + cfg.offset_v
    # What the comparator would decide at each clock instant.
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
    """Expand per-edge codes to a sample-and-hold waveform (matches ``v_code``)."""
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
    """Simulate a slow ramp capture for INL/DNL analysis."""
    noise_cfg = noise or AdcNoiseConfig()
    # Deeper dwell reduces histogram variance when thermal noise dithers codes.
    if noise_cfg.enabled and samples_per_code < 16:
        samples_per_code = 16

    num_samples = cfg.num_codes * samples_per_code
    dt = 1.0 / cfg.fs_hz
    time = np.arange(num_samples, dtype=np.float64) * dt

    margin = 0.5 * cfg.lsb
    # Ramp between code centers so each code is hit equally (no saturation pile-up).
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
    """Simulate a coherent sine capture for FFT analysis."""
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
