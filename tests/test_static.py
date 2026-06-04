"""Tests for INL/DNL analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

from adc_model.config import AdcConfig
from adc_model.model import simulate_static
from adc_model.static import compute_inl_dnl, decode_codes

if TYPE_CHECKING:
    from _pytest.fixtures import FixtureRequest


def test_ideal_adc_inl_dnl_near_zero() -> None:
    """An ideal ADC should produce near-zero INL/DNL on a ramp test."""
    cfg = AdcConfig(bits=8, gain=1.0, offset_v=0.0)
    data = simulate_static(cfg, samples_per_code=8)
    codes = decode_codes(data["v_code"], cfg)
    result = compute_inl_dnl(data["vin"], codes, cfg)
    assert result.max_dnl_lsb < 0.25
    assert result.max_inl_lsb < 0.6
