"""Tests for ADC noise contributions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from adc_model.config import AdcConfig, AdcNoiseConfig
from adc_model.dynamic import compute_dynamic_metrics
from adc_model.model import simulate_dynamic, simulate_static
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
