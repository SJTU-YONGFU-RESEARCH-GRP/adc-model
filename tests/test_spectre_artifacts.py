"""Tests for Spectre run-directory and artifact cleanup."""

from __future__ import annotations

from pathlib import Path

from adc_model.config import AdcConfig, AdcNoiseConfig
from adc_model.spectre_engine import (
    cleanup_spectre_artifacts,
    prepare_spectre_veriloga,
    render_spectre_netlist,
    spectre_capture_num_edges,
)


def test_render_spectre_netlist_uses_absolute_veriloga_path(tmp_path: Path) -> None:
    """Rendered netlists should not depend on launching Spectre from repo root."""
    repo_root = tmp_path / "repo"
    template = repo_root / "testbench/spectre/static_inl_dnl.scs"
    template.parent.mkdir(parents=True)
    template.write_text(
        'include "./testbench/spectre/adc_include.scs"\nparameters bits=10\n',
        encoding="utf-8",
    )
    (repo_root / "veriloga").mkdir()
    (repo_root / "veriloga/configurable_adc.va").write_text("// stub\n", encoding="utf-8")

    rendered = render_spectre_netlist(
        template,
        cfg=AdcConfig(bits=10),
        noise=AdcNoiseConfig(),
        repo_root=repo_root,
    )
    assert 'include "./testbench/spectre/adc_include.scs"' not in rendered
    assert "ahdl_include" in rendered
    assert "configurable_adc.va" in rendered


def test_prepare_spectre_veriloga_writes_python_dnl_include(tmp_path: Path) -> None:
    """Noisy Spectre runs should render a Python-matched DNL include beside the VA."""
    repo_root = tmp_path / "repo"
    va_dir = repo_root / "veriloga"
    va_dir.mkdir(parents=True)
    (va_dir / "configurable_adc.va").write_text(
        "`ifdef CONFIGURABLE_ADC_USE_PYTHON_DNL\n`include \"dnl_profile.inc\"\n`endif\n",
        encoding="utf-8",
    )
    run_dir = tmp_path / "logs"
    cfg = AdcConfig(bits=8)
    noise = AdcNoiseConfig(dnl_sigma_lsb=0.05, noise_seed=4, sigma_thermal_v=1.0e-3)
    va_path = prepare_spectre_veriloga(repo_root, run_dir, cfg, noise, num_edges=32)
    rendered_va = va_path.read_text(encoding="utf-8")
    include_path = run_dir / "netlists" / "dnl_profile.inc"
    edge_noise_path = run_dir / "netlists" / "edge_noise.inc"
    assert "`define CONFIGURABLE_ADC_USE_PYTHON_DNL" in rendered_va
    assert "`define CONFIGURABLE_ADC_USE_PYTHON_NOISE" in rendered_va
    assert include_path.is_file()
    assert edge_noise_path.is_file()
    assert "dnl_offset[0]" in include_path.read_text(encoding="utf-8")
    assert "edge_noise_count = 32;" in edge_noise_path.read_text(encoding="utf-8")


def test_spectre_capture_num_edges_matches_static_ramp_depth() -> None:
    """Static Spectre captures should use the same edge count as Python simulate_static."""
    cfg = AdcConfig(bits=10)
    noise = AdcNoiseConfig(sigma_thermal_v=250e-6, dnl_sigma_lsb=0.08)
    assert spectre_capture_num_edges(
        cfg,
        noise,
        netlist_stem="static_inl_dnl",
        samples_per_code=4,
        num_samples=None,
    ) == cfg.num_codes * 16


def test_cleanup_spectre_artifacts_removes_status_and_cache(tmp_path: Path) -> None:
    """Cleanup should remove Spectre ``status`` and ``.ahdlSimDB`` folders."""
    run_dir = tmp_path / "logs"
    run_dir.mkdir()
    (run_dir / "status").write_text("ok\n", encoding="utf-8")
    cache = run_dir / "static_inl_dnl.ahdlSimDB"
    cache.mkdir()
    (cache / "marker.txt").write_text("x\n", encoding="utf-8")

    cleanup_spectre_artifacts(run_dir, "static_inl_dnl")
    assert not (run_dir / "status").exists()
    assert not cache.exists()
