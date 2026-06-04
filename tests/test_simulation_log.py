"""Tests for simulation logging utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from adc_model.config import AdcConfig, AdcNoiseConfig
from adc_model.simulation_log import (
    archive_veriloga_artifacts,
    prepare_output_dirs,
    write_python_simulation_log,
)

if TYPE_CHECKING:
    from _pytest.fixtures import FixtureRequest
    from pytest_mock.plugin import MockerFixture


def test_write_python_simulation_log(tmp_path) -> None:
    """Python simulation logs should include config and result sections."""
    log_path = tmp_path / "logs" / "python_static.log"
    write_python_simulation_log(
        log_path,
        test_name="static_inl_dnl",
        cfg=AdcConfig(bits=10),
        noise=AdcNoiseConfig(sigma_thermal_v=250e-6),
        test_params={"samples_per_code": 16},
        results={"max_dnl_lsb": 0.12},
    )
    text = log_path.read_text(encoding="utf-8")
    assert "Python simulation log: static_inl_dnl" in text
    assert "bits=10" in text
    assert "sigma_thermal_v=0.00025" in text
    assert "max_dnl_lsb=0.12" in text


def test_archive_veriloga_artifacts(tmp_path) -> None:
    """Verilog-A model and testbench files should be copied into the output folder."""
    repo_root = tmp_path / "repo"
    va_dir = repo_root / "veriloga"
    tb_dir = repo_root / "testbench/spectre"
    va_dir.mkdir(parents=True)
    tb_dir.mkdir(parents=True)
    (va_dir / "configurable_adc.va").write_text("// adc model", encoding="utf-8")
    (tb_dir / "adc_include.scs").write_text("// include", encoding="utf-8")
    (tb_dir / "static_inl_dnl.scs").write_text("// static", encoding="utf-8")
    (tb_dir / "dynamic_spectrum.scs").write_text("// dynamic", encoding="utf-8")

    output_dir = tmp_path / "outputs" / "run"
    model_path = archive_veriloga_artifacts(repo_root, output_dir)
    assert model_path.is_file()
    assert (output_dir / "veriloga" / "static_inl_dnl.scs").is_file()
    assert prepare_output_dirs(output_dir).logs_dir.is_dir()
