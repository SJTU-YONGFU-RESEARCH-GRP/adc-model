"""Tests for ADC noise contributions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from adc_model.config import AdcConfig, AdcNoiseConfig
from adc_model.dynamic import compute_dynamic_metrics
from adc_model.model import simulate_dynamic, simulate_static
from adc_model.noise import build_dnl_profile, build_edge_normal_draws, write_dnl_profile_include, write_edge_noise_include
from adc_model.static import compute_inl_dnl, decode_codes

if TYPE_CHECKING:
    from _pytest.fixtures import FixtureRequest


def test_thermal_noise_reduces_sndr() -> None:
    """Thermal noise should lower SNDR compared with an ideal ADC."""
    cfg = AdcConfig(bits=10, gain=1.0, offset_v=0.0, fs_hz=1.0e6)
    ideal = simulate_dynamic(cfg, num_samples=8192, coherent_bin=997, noise=AdcNoiseConfig())
    noisy = simulate_dynamic(
        cfg,
        num_samples=8192,
        coherent_bin=997,
        noise=AdcNoiseConfig(sigma_thermal_v=1.0e-3, noise_seed=2),
    )
    fin_hz = float(ideal["fin_hz"][0])
    ideal_metrics = compute_dynamic_metrics(decode_codes(ideal["v_code"], cfg), cfg, fin_hz=fin_hz)
    noisy_metrics = compute_dynamic_metrics(decode_codes(noisy["v_code"], cfg), cfg, fin_hz=fin_hz)
    assert noisy_metrics.sndr_db < ideal_metrics.sndr_db


def test_dnl_profile_increases_static_spread() -> None:
    """Per-code DNL spread should increase static linearity error."""
    cfg = AdcConfig(bits=8, gain=1.0, offset_v=0.0)
    ideal = simulate_static(cfg, samples_per_code=16, noise=AdcNoiseConfig())
    noisy = simulate_static(
        cfg,
        samples_per_code=16,
        noise=AdcNoiseConfig(dnl_sigma_lsb=0.15, noise_seed=3),
    )
    ideal_result = compute_inl_dnl(
        ideal["vin"],
        decode_codes(ideal["v_code"], cfg),
        cfg,
        method="histogram",
    )
    noisy_result = compute_inl_dnl(
        noisy["vin"],
        decode_codes(noisy["v_code"], cfg),
        cfg,
        method="histogram",
    )
    assert noisy_result.max_dnl_lsb > ideal_result.max_dnl_lsb


def test_write_dnl_profile_include_matches_build_dnl_profile(tmp_path) -> None:
    """Spectre DNL include should mirror Python build_dnl_profile values."""
    cfg = AdcConfig(bits=8)
    noise = AdcNoiseConfig(dnl_sigma_lsb=0.1, noise_seed=9)
    include_path = tmp_path / "dnl_profile.inc"
    write_dnl_profile_include(cfg, noise, include_path)
    profile = build_dnl_profile(cfg, noise)
    text = include_path.read_text(encoding="utf-8")
    for code_idx, value in enumerate(profile):
        assert f"dnl_offset[{code_idx}] = {value:.16e};" in text


def test_build_edge_normal_draws_respects_enable_flags() -> None:
    """Jitter and thermal draws should follow the same order as the edge front end."""
    noise = AdcNoiseConfig(
        sigma_thermal_v=250e-6,
        jitter_rms_s=500e-15,
        noise_seed=11,
    )
    jitter, thermal = build_edge_normal_draws(noise, num_edges=4)
    rng = np.random.default_rng(noise.noise_seed)
    expected_jitter: list[float] = []
    expected_thermal: list[float] = []
    for _ in range(4):
        expected_jitter.append(float(rng.normal()))
        expected_thermal.append(float(rng.normal()))
    np.testing.assert_allclose(jitter, np.array(expected_jitter, dtype=np.float64))
    np.testing.assert_allclose(thermal, np.array(expected_thermal, dtype=np.float64))


def test_write_edge_noise_include_exports_draw_tables(tmp_path) -> None:
    """Spectre edge-noise include should list Python normal draws by edge index."""
    noise = AdcNoiseConfig(sigma_thermal_v=1.0e-3, jitter_rms_s=2.0e-12, noise_seed=5)
    include_path = tmp_path / "edge_noise.inc"
    write_edge_noise_include(noise, num_edges=3, path=include_path)
    jitter, thermal = build_edge_normal_draws(noise, num_edges=3)
    text = include_path.read_text(encoding="utf-8")
    assert "edge_noise_count = 3;" in text
    for edge in range(3):
        assert f"jitter_normal[{edge}] = {jitter[edge]:.16e};" in text
        assert f"thermal_normal[{edge}] = {thermal[edge]:.16e};" in text
