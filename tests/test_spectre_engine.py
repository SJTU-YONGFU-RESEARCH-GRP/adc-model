"""Tests for Spectre nutascii waveform parsing."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from adc_model.config import AdcConfig, AdcNoiseConfig
from adc_model.spectre_engine import (
    prepare_spectre_waveform,
    read_spectre_nutascii,
    render_spectre_netlist,
)


def test_read_spectre_nutascii_parses_multi_line_continuations(tmp_path: Path) -> None:
    """TI-style nutascii with several tab-prefixed rows per sample should parse."""
    raw = tmp_path / "ti_tran.nutascii"
    raw.write_text(
        "\n".join(
            [
                "Plotname: Transient Analysis",
                "No. Variables: 6",
                "Variables:\t0\ttime\ts",
                "\t\t1\tvin\tV",
                "\t\t2\tclk_mux\tV",
                "\t\t3\tclk0\tV",
                "\t\t4\tclk1\tV",
                "\t\t5\tv_code0\tV",
                "Values:",
                " 0\t0\t0.1\t0",
                "\t0\t0.5",
                "\t1.5",
                " 1\t1e-9\t0.2\t1",
                "\t1\t1.5",
                "\t2.5",
            ]
        ),
        encoding="utf-8",
    )
    data = read_spectre_nutascii(raw)
    np.testing.assert_allclose(data["time"], [0.0, 1e-9])
    np.testing.assert_allclose(data["vin"], [0.1, 0.2])
    np.testing.assert_allclose(data["clk_mux"], [0.0, 1.0])
    np.testing.assert_allclose(data["clk0"], [0.0, 1.0])
    np.testing.assert_allclose(data["clk1"], [0.5, 1.5])
    np.testing.assert_allclose(data["v_code0"], [1.5, 2.5])


def test_read_spectre_nutascii_parses_split_rows(tmp_path: Path) -> None:
    """Nutascii rows with a follow-on line per sample should parse correctly."""
    raw = tmp_path / "tran.nutascii"
    raw.write_text(
        "\n".join(
            [
                "Plotname: Transient Analysis",
                "No. Variables: 4",
                "Variables:\t0\ttime\ts",
                "\t\t1\tvin\tV",
                "\t\t2\tclk\tV",
                "\t\t3\tv_code\tV",
                "Values:",
                " 0\t0\t0.1\t0",
                "\t0.5",
                " 1\t1e-9\t0.2\t1",
                "\t1.5",
            ]
        ),
        encoding="utf-8",
    )
    data = read_spectre_nutascii(raw)
    np.testing.assert_allclose(data["time"], [0.0, 1e-9])
    np.testing.assert_allclose(data["vin"], [0.1, 0.2])
    np.testing.assert_allclose(data["clk"], [0.0, 1.0])
    np.testing.assert_allclose(data["v_code"], [0.5, 1.5])


def test_render_spectre_netlist_uses_effective_samples_per_code(tmp_path: Path) -> None:
    """Noisy static runs should match Python/ngspice ramp depth (16 samples/code)."""
    template = (
        Path(__file__).resolve().parents[1]
        / "testbench/spectre/static_inl_dnl.scs"
    )
    cfg = AdcConfig(bits=10)
    noise = AdcNoiseConfig(sigma_thermal_v=250e-6, dnl_sigma_lsb=0.08)
    rendered = render_spectre_netlist(
        template,
        cfg=cfg,
        noise=noise,
        samples_per_code=4,
    )
    assert "parameters samples_per_code=16" in rendered
    assert "parameters num_samples=16384" in rendered


def test_render_spectre_netlist_disables_noise_for_ideal(tmp_path: Path) -> None:
    """Rendered ideal netlists should zero out noise parameters."""
    template = (
        Path(__file__).resolve().parents[1]
        / "testbench/spectre/dynamic_spectrum.scs"
    )
    cfg = AdcConfig(bits=10)
    noise = AdcNoiseConfig()
    rendered = render_spectre_netlist(
        template,
        cfg=cfg,
        noise=noise,
        num_samples=8192,
        coherent_bin=997,
    )
    assert "parameters sigma_thermal=0.0" in rendered
    assert "parameters dnl_sigma_lsb=0.0" in rendered


def test_prepare_spectre_waveform_aligns_to_clock_edges(tmp_path: Path) -> None:
    """Dense transient output should align to clk edges, not a uniform time grid."""
    fixture = (
        Path(__file__).resolve().parents[1]
        / "outputs"
        / "spectre_ideal_fixed"
        / "logs"
        / "dynamic_spectrum.nutascii"
    )
    if not fixture.is_file():
        pytest.skip("Spectre raw fixture not generated on this machine")
    raw = read_spectre_nutascii(fixture)
    prepared = prepare_spectre_waveform(raw, fs_hz=1.0e6, max_samples=8192)
    assert len(prepared["time"]) == 8192
    dt = float(np.median(np.diff(prepared["time"])))
    assert abs(dt - 1.0e-6) < 1.0e-9
    assert np.max(prepared["clk"]) > 0.5


def test_read_spectre_nutascii_fixture(tmp_path: Path) -> None:
    """A captured Spectre raw file should round-trip through the parser."""
    fixture = (
        Path(__file__).resolve().parents[1] / "outputs" / "spectre_test_raw"
    )
    if not fixture.is_file():
        pytest.skip("Spectre raw fixture not generated on this machine")
    data = read_spectre_nutascii(fixture)
    assert len(data["time"]) > 1000
    assert set(data) >= {"time", "vin", "clk", "v_code"}
