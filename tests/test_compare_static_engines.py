"""Tests for static engine comparison helper."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from adc_model.config import AdcConfig
from adc_model.io import write_waveform_csv
from adc_model.static_compare import analyze_static_waveform


def test_analyze_static_waveform_reads_csv(tmp_path: Path) -> None:
    """A minimal static CSV should produce finite summary statistics."""
    cfg = AdcConfig(bits=6)
    num_samples = cfg.num_codes * 4
    codes = np.repeat(np.arange(cfg.num_codes), 4)
    data = {
        "time": np.arange(num_samples, dtype=np.float64) / cfg.fs_hz,
        "vin": np.linspace(cfg.vrefn, cfg.vrefp, num_samples),
        "clk": np.ones(num_samples),
        "v_code": codes.astype(np.float64) * cfg.lsb,
    }
    csv_path = tmp_path / "static_waveform.csv"
    write_waveform_csv(csv_path, data)

    stats = analyze_static_waveform("python", csv_path, cfg, inl_dnl_method="histogram")
    assert stats.num_samples == num_samples
    assert stats.transitions > 0
    assert np.isfinite(stats.max_dnl_lsb)
