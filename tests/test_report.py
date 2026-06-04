"""Tests for markdown report generation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from adc_model.config import AdcConfig, AdcNoiseConfig
from adc_model.dynamic import DynamicMetrics, HarmonicTone
from adc_model.report import (
    DynamicTestConfig,
    SimulationReport,
    StaticTestConfig,
    render_report_markdown,
    write_report,
)
from adc_model.static import StaticLinearity

if TYPE_CHECKING:
    from _pytest.fixtures import FixtureRequest


def test_report_contains_configuration_and_metrics(tmp_path: Path) -> None:
    """Generated markdown should include config tables and result metrics."""
    output_dir = tmp_path / "sim"
    output_dir.mkdir()
    static_plot = output_dir / "inl_dnl.svg"
    dynamic_plot = output_dir / "spectrum.svg"
    static_plot.write_text("<svg/>", encoding="utf-8")
    dynamic_plot.write_text("<svg/>", encoding="utf-8")
    static_csv = output_dir / "static_waveform.csv"
    dynamic_csv = output_dir / "dynamic_waveform.csv"
    static_csv.write_text("time,vin,clk,v_code,code\n0,0,0,0,0\n", encoding="utf-8")
    dynamic_csv.write_text("time,vin,clk,v_code,code\n0,0,0,0,0\n", encoding="utf-8")

    report = SimulationReport(
        adc=AdcConfig(bits=10),
        noise=AdcNoiseConfig(sigma_thermal_v=250e-6),
        static_cfg=StaticTestConfig(samples_per_code=16, inl_dnl_method="histogram", engine="Python"),
        dynamic_cfg=DynamicTestConfig(
            num_samples=8192,
            coherent_bin=997,
            fin_hz=121704.1015625,
            engine="Python",
        ),
        static_result=StaticLinearity(
            codes=np.arange(1, 1022, dtype=np.int64),
            dnl_lsb=np.zeros(1021),
            inl_lsb=np.zeros(1021),
            max_dnl_lsb=0.12,
            max_inl_lsb=0.34,
        ),
        dynamic_result=DynamicMetrics(
            freq_hz=np.array([0.0, 1.0]),
            magnitude_dbfs=np.array([-120.0, -3.0]),
            fin_hz=121704.1015625,
            signal_bin=997,
            harmonics=(
                HarmonicTone(
                    order=1,
                    bin_index=997,
                    freq_hz=121704.1015625,
                    magnitude_dbfs=-3.0,
                    aliased=False,
                ),
            ),
            sndr_db=58.5,
            sfdr_db=80.0,
            enob_bits=9.4,
            thd_db=75.0,
        ),
        static_plot=static_plot,
        dynamic_plot=dynamic_plot,
        static_csv=static_csv,
        dynamic_csv=dynamic_csv,
        generated_at=datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    report_path = output_dir / "REPORT.md"
    write_report(report, report_path)
    markdown = report_path.read_text(encoding="utf-8")

    assert "ADC Simulation Report" in markdown
    assert "250 uV" in markdown
    assert "Max DNL (abs)" in markdown
    assert "58.50 dB" in markdown
    assert "![INL/DNL plot](inl_dnl.svg)" in markdown
    assert "![Dynamic spectrum](spectrum.svg)" in markdown
    assert render_report_markdown(report, report_path) == markdown
