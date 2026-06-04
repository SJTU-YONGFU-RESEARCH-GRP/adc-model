"""Cross-engine parity checks for Python vs ngspice."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from adc_model.config import AdcConfig, AdcNoiseConfig
from adc_model.dynamic import compute_dynamic_metrics
from adc_model.model import simulate_dynamic, simulate_static
from adc_model.ngspice_engine import run_dynamic_testbench, run_static_testbench
from adc_model.static import compute_inl_dnl, decode_codes
from adc_model.static_compare import resolve_inl_dnl_method


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not installed")
def test_python_ngspice_default_metrics_are_close(tmp_path: Path) -> None:
    """Default-noise Python and ngspice runs should agree within tight tolerance."""
    cfg = AdcConfig(bits=10, gain=1.01, offset_v=5e-3)
    noise = AdcNoiseConfig(
        sigma_thermal_v=250e-6,
        jitter_rms_s=500e-15,
        nonlinearity_a3=-0.002,
        dnl_sigma_lsb=0.08,
        noise_seed=1,
    )
    output_dir = tmp_path / "parity"

    static_method = resolve_inl_dnl_method(noise, "auto")
    py_static = simulate_static(cfg, samples_per_code=4, noise=noise)
    py_static_result = compute_inl_dnl(
        py_static["vin"],
        decode_codes(py_static["v_code"], cfg),
        cfg,
        method=static_method,
    )
    py_dynamic = simulate_dynamic(cfg, num_samples=2048, coherent_bin=311, noise=noise)
    py_dynamic_result = compute_dynamic_metrics(
        decode_codes(py_dynamic["v_code"], cfg),
        cfg,
        fin_hz=float(py_dynamic["fin_hz"][0]),
    )

    ng_static = run_static_testbench(
        output_dir=output_dir,
        cfg=cfg,
        noise=noise,
        samples_per_code=4,
        log_path=output_dir / "logs" / "ngspice_static.log",
    )
    ng_static_result = compute_inl_dnl(
        ng_static["vin"],
        decode_codes(ng_static["v_code"], cfg),
        cfg,
        method=static_method,
    )
    fin_hz = 311 * cfg.fs_hz / 2048
    ng_dynamic = run_dynamic_testbench(
        output_dir=output_dir,
        cfg=cfg,
        noise=noise,
        num_samples=2048,
        fin_hz=fin_hz,
        log_path=output_dir / "logs" / "ngspice_dynamic.log",
    )
    ng_dynamic_result = compute_dynamic_metrics(
        decode_codes(ng_dynamic["v_code"], cfg),
        cfg,
        fin_hz=fin_hz,
    )

    assert abs(py_static_result.max_dnl_lsb - ng_static_result.max_dnl_lsb) < 0.02
    assert abs(py_static_result.max_inl_lsb - ng_static_result.max_inl_lsb) < 0.02
    assert abs(py_dynamic_result.sndr_db - ng_dynamic_result.sndr_db) < 1.0
    assert abs(py_dynamic_result.enob_bits - ng_dynamic_result.enob_bits) < 0.2
