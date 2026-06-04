"""Tests for static ramp ADC edge indices."""

from __future__ import annotations

import numpy as np

from adc_model.io import adc_capture_edge_indices, clock_pulse_waveform, static_capture_edge_indices


def test_static_capture_edge_indices_stride_on_uniform_grid() -> None:
    """Static ramps sample every clock period on a uniform ``1/fs`` grid."""
    fs_hz = 1.0e6
    num_samples = 256
    time = np.arange(num_samples, dtype=np.float64) / fs_hz
    clk = clock_pulse_waveform(time, fs_hz)
    edges = static_capture_edge_indices(
        num_samples,
        clk,
        samples_per_code=16,
        time=time,
        fs_hz=fs_hz,
    )
    expected = adc_capture_edge_indices(time, fs_hz, clk)
    np.testing.assert_array_equal(edges, expected)
    assert len(edges) == num_samples
