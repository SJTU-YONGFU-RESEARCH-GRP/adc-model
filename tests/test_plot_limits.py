"""Tests for plot axis limit helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from adc_model.dynamic import HarmonicTone, _estimate_noise_floor_dbfs
from adc_model.static import _data_ylim

if TYPE_CHECKING:
    from _pytest.fixtures import FixtureRequest


def test_data_ylim_frames_values() -> None:
    """INL/DNL y-limits should follow the plotted data range."""
    values = np.array([-0.4, -0.1, 0.2, 0.5], dtype=np.float64)
    ymin, ymax = _data_ylim(values)
    assert ymin < values.min()
    assert ymax > values.max()
    assert ymax - ymin < 1.5


def test_noise_floor_estimate_excludes_tones() -> None:
    """Spectrum noise floor should be estimated from non-tone bins."""
    magnitude = np.full(128, -90.0)
    magnitude[10] = 0.0
    magnitude[20] = -20.0
    harmonics = (
        HarmonicTone(order=1, bin_index=10, freq_hz=1e5, magnitude_dbfs=0.0, aliased=False),
        HarmonicTone(order=2, bin_index=20, freq_hz=2e5, magnitude_dbfs=-20.0, aliased=False),
    )
    floor = _estimate_noise_floor_dbfs(magnitude, harmonics)
    assert -92.0 <= floor <= -85.0
