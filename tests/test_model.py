"""Tests for the behavioral ADC model."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from adc_model.config import AdcConfig
from adc_model.model import quantize_sample, simulate_dynamic, simulate_static

if TYPE_CHECKING:
    from _pytest.fixtures import FixtureRequest


def test_ideal_adc_midscale_code() -> None:
    """Mid-scale input should map to the center code for an ideal ADC."""
    cfg = AdcConfig(bits=10, vrefp=1.0, vrefn=0.0)
    code = quantize_sample(0.5, cfg)
    assert code == 512


def test_static_simulation_has_expected_length() -> None:
    """Static capture length should equal codes times samples-per-code."""
    cfg = AdcConfig(bits=8)
    data = simulate_static(cfg, samples_per_code=3)
    assert len(data["code"]) == cfg.num_codes * 3


def test_dynamic_simulation_is_coherent() -> None:
    """Dynamic capture should preserve the requested coherent tone bin."""
    cfg = AdcConfig(bits=10, fs_hz=1.0e6)
    num_samples = 4096
    coherent_bin = 503
    data = simulate_dynamic(cfg, num_samples=num_samples, coherent_bin=coherent_bin)
    fin_hz = float(data["fin_hz"][0])
    assert abs(fin_hz - coherent_bin * cfg.fs_hz / num_samples) < 1.0
