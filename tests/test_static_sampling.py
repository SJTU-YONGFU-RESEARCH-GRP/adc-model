"""Tests for clock-aligned static ramp sampling."""

from __future__ import annotations

import numpy as np

from adc_model.config import AdcConfig, AdcNoiseConfig
from adc_model.io import adc_capture_edge_indices, static_capture_edge_indices
from adc_model.model import simulate_static
from adc_model.static import compute_inl_dnl, decode_codes


def test_static_capture_edges_match_va_per_clock_policy() -> None:
    """Static edge indices should align with one sample per clock period."""
    fs_hz = 1.0e6
    num_samples = 64
    time = np.arange(num_samples, dtype=np.float64) / fs_hz
    from adc_model.io import clock_pulse_waveform

    clk = clock_pulse_waveform(time, fs_hz)
    static_edges = static_capture_edge_indices(
        num_samples,
        clk,
        samples_per_code=16,
        time=time,
        fs_hz=fs_hz,
    )
    adc_edges = adc_capture_edge_indices(time, fs_hz, clk)
    np.testing.assert_array_equal(static_edges, adc_edges)


def test_static_noisy_samples_every_clock_edge() -> None:
    """Noisy static ramps re-quantize every clock (matches configurable_adc.va)."""
    cfg = AdcConfig(bits=10, gain=1.01, offset_v=5e-3)
    noise = AdcNoiseConfig(
        sigma_thermal_v=250e-6,
        dnl_sigma_lsb=0.08,
        nonlinearity_a3=-0.002,
        noise_seed=1,
    )
    samples_per_code = 16
    data = simulate_static(cfg, samples_per_code=samples_per_code, noise=noise)
    expected_samples = cfg.num_codes * samples_per_code
    assert len(data["vin"]) == expected_samples
    codes = decode_codes(data["v_code"], cfg)
    interior = codes[(codes > 0) & (codes < cfg.max_code)]
    assert len(np.unique(interior)) > cfg.max_code // 2


def test_ideal_static_matches_va_style_code_updates() -> None:
    """Ideal ramps should update held codes mid-dwell when the input crosses a bin."""
    cfg = AdcConfig(bits=10, gain=1.0, offset_v=0.0)
    data = simulate_static(cfg, samples_per_code=4)
    codes = decode_codes(data["v_code"], cfg)
    transitions = int(np.sum(codes[1:] != codes[:-1]))
    result = compute_inl_dnl(data["vin"], codes, cfg, method="auto")
    assert transitions > cfg.max_code // 4
    assert result.max_dnl_lsb < 0.5


def test_static_histogram_dnl_in_family_with_edge_sampling() -> None:
    """Histogram DNL should stay in a moderate LSB range after per-clock sampling."""
    cfg = AdcConfig(bits=10, gain=1.01, offset_v=5e-3)
    noise = AdcNoiseConfig(
        sigma_thermal_v=250e-6,
        dnl_sigma_lsb=0.08,
        nonlinearity_a3=-0.002,
        noise_seed=1,
    )
    data = simulate_static(cfg, samples_per_code=16, noise=noise)
    result = compute_inl_dnl(
        data["vin"],
        decode_codes(data["v_code"], cfg),
        cfg,
        method="histogram",
    )
    assert 0.05 < result.max_dnl_lsb < 2.0
    assert result.max_inl_lsb < 5.0
