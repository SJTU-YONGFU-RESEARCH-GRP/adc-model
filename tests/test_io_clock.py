"""Tests for clock period and edge-aligned waveform downsampling."""

from __future__ import annotations

import numpy as np

from adc_model.io import (
    adc_capture_edge_indices,
    clock_pulse_waveform,
    prepare_edge_aligned_waveform,
    uniform_fs_sample_indices,
)


def test_clock_pulse_period_matches_fs() -> None:
    """Clock high/low intervals should repeat with period ``1/fs``."""
    fs_hz = 1.0e6
    dt = 1.0 / fs_hz
    time = np.arange(16, dtype=np.float64) * dt
    clk = clock_pulse_waveform(time, fs_hz)
    period = 1.0 / fs_hz
    assert abs(float(np.median(np.diff(time))) - period) < 1.0e-15
    assert np.all((clk == 0.0) | (clk == 1.0))
    assert np.any(clk > 0.5) and np.any(clk <= 0.5)


def test_adc_capture_edge_indices_on_uniform_fs_grid() -> None:
    """One sample per ``1/fs`` timestep should yield one conversion per index."""
    fs_hz = 2.0e6
    dt = 1.0 / fs_hz
    time = np.arange(32, dtype=np.float64) * dt
    clk = clock_pulse_waveform(time, fs_hz)
    edges = adc_capture_edge_indices(time, fs_hz, clk)
    expected = uniform_fs_sample_indices(len(time), time, fs_hz)
    np.testing.assert_array_equal(edges, expected)


def test_prepare_edge_aligned_waveform_dense_spectre_style() -> None:
    """Dense transients should downsample on clk rising edges with v_code lag."""
    fs_hz = 1.0e6
    period = 1.0 / fs_hz
    dt_dense = period / 4.0
    num_dense = 32
    time = np.arange(num_dense, dtype=np.float64) * dt_dense
    clk = clock_pulse_waveform(time, fs_hz)
    v_code = np.arange(num_dense, dtype=np.float64)
    prepared = prepare_edge_aligned_waveform(
        {"time": time, "vin": time, "clk": clk, "v_code": v_code},
        fs_hz,
        max_samples=8,
    )
    assert 1 <= len(prepared["time"]) <= 8
    if len(prepared["time"]) > 1:
        assert abs(float(np.median(np.diff(prepared["time"]))) - period) < 1.0e-12
