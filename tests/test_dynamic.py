"""Tests for dynamic FFT analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

from adc_model.dynamic import compute_dynamic_metrics
from adc_model.model import AdcConfig, simulate_dynamic
from adc_model.static import decode_codes

if TYPE_CHECKING:
    from _pytest.fixtures import FixtureRequest


def test_dynamic_metrics_for_ideal_adc() -> None:
    """An ideal ADC should report reasonable SNDR/ENOB on a full-scale tone."""
    cfg = AdcConfig(bits=10, gain=1.0, offset_v=0.0, fs_hz=1.0e6)
    data = simulate_dynamic(cfg, num_samples=8192, coherent_bin=997)
    codes = decode_codes(data["v_code"], cfg)
    fin_hz = float(data["fin_hz"][0])
    metrics = compute_dynamic_metrics(codes, cfg, fin_hz=fin_hz)
    assert metrics.sndr_db > 55.0
    assert metrics.enob_bits > 8.5


def test_nonlinearity_identifies_harmonics() -> None:
    """Third-order nonlinearity should produce identifiable H2/H3 tones."""
    from adc_model.config import AdcNoiseConfig
    from adc_model.model import simulate_dynamic

    cfg = AdcConfig(bits=10, gain=1.0, offset_v=0.0, fs_hz=1.0e6)
    noise = AdcNoiseConfig(nonlinearity_a3=-0.01)
    data = simulate_dynamic(cfg, num_samples=8192, coherent_bin=997, noise=noise)
    codes = decode_codes(data["v_code"], cfg)
    fin_hz = float(data["fin_hz"][0])
    metrics = compute_dynamic_metrics(codes, cfg, fin_hz=fin_hz, min_harmonic_dbfs=-100.0)
    orders = {tone.order for tone in metrics.harmonics}
    assert 1 in orders
    assert len(orders.intersection({2, 3})) >= 1
