"""Tests for Spectre run-directory and artifact cleanup."""

from __future__ import annotations

from pathlib import Path

from adc_model.config import AdcConfig, AdcNoiseConfig
from adc_model.spectre_engine import (
    cleanup_spectre_artifacts,
    render_spectre_netlist,
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
