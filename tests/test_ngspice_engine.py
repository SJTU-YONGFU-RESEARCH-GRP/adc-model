"""Tests for ngspice netlist generation."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import numpy as np

from adc_model.config import AdcConfig, AdcNoiseConfig
from adc_model.ngspice_engine import (
    render_dynamic_netlist,
    render_static_netlist,
    run_ngspice_netlist,
    write_coherent_sine_pwl,
)


def test_render_static_netlist_includes_ramp_and_adc() -> None:
    """Static netlists should include ramp stimulus and behavioral ADC."""
    cfg = AdcConfig(bits=10)
    noise = AdcNoiseConfig()
    text = render_static_netlist(cfg, noise, samples_per_code=4, include_dir=Path("/tmp"))
    assert "Vin vin 0 PWL(" in text
    assert "Bnonlin v_nl" in text
    assert "Btherm" not in text
    assert ".param BITS=10" in text
    assert "wrdata" in text


def test_render_dynamic_netlist_uses_inline_pwl() -> None:
    """Dynamic netlists should use a coherent inline PWL stimulus."""
    cfg = AdcConfig(bits=10)
    noise = AdcNoiseConfig()
    text = render_dynamic_netlist(
        cfg,
        noise,
        num_samples=128,
        fin_hz=100_000.0,
        include_dir=Path("/tmp"),
    )
    assert "Vin vin 0 PWL(" in text
    assert ".param FIN=100000.0" in text


def test_write_coherent_sine_pwl(tmp_path: Path) -> None:
    """Coherent sine PWL files should contain one line per sample."""
    cfg = AdcConfig(bits=10, fs_hz=1.0e6)
    path = tmp_path / "stimulus.pwl"
    write_coherent_sine_pwl(path, cfg, num_samples=16, fin_hz=125_000.0)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 16


def test_render_static_netlist_matches_python_signal_order() -> None:
    """Static netlists should follow the Python / Verilog-A signal order."""
    cfg = AdcConfig(bits=10)
    noise = AdcNoiseConfig(jitter_rms_s=500e-15, dnl_sigma_lsb=0.08)
    text = render_static_netlist(cfg, noise, samples_per_code=4, include_dir=Path("/tmp"))
    assert "Bgain v_gain" in text
    assert "Bnonlin v_nl" in text
    assert "Bcal" not in text
    assert "NONLINEARITY_A2*pow((V(v_gain)-VCM)/VFS,2)" in text
    assert "Vin vin 0 PWL(" in text


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not installed")
def test_run_ngspice_static_smoke(tmp_path: Path) -> None:
    """Run a minimal static netlist through ngspice when available."""
    cfg = AdcConfig(bits=6, fs_hz=1.0e6)
    noise = AdcNoiseConfig(sigma_thermal_v=0.0, nonlinearity_a3=0.0)
    include_dir = tmp_path / "includes"
    netlist = render_static_netlist(cfg, noise, samples_per_code=2, include_dir=include_dir)
    num_samples = cfg.num_codes * 2
    result = run_ngspice_netlist(
        netlist_text=netlist,
        netlist_path=tmp_path / "static.cir",
        wrdata_path=tmp_path / "static.wrdata",
        csv_path=tmp_path / "static.csv",
        log_path=tmp_path / "static.log",
        fs_hz=cfg.fs_hz,
        include_dir=include_dir,
        cfg=cfg,
        noise=noise,
        max_samples=num_samples,
    )
    assert result.csv_path.is_file()
    assert result.wrdata_path.stat().st_size > 0
    log_text = result.log_path.read_text(encoding="utf-8")
    assert "ngspice simulation log" in log_text
    table = np.loadtxt(result.csv_path, delimiter=",", skiprows=1)
    assert table.shape[0] == num_samples
