"""Configurable ADC behavioral model and testbench analysis."""

from adc_model.config import AdcConfig, AdcNoiseConfig
from adc_model.dynamic import DynamicMetrics, HarmonicTone, compute_dynamic_metrics
from adc_model.model import simulate_dynamic, simulate_static
from adc_model.report import SimulationReport, write_report
from adc_model.static import StaticLinearity, compute_inl_dnl

__all__ = [
    "AdcConfig",
    "AdcNoiseConfig",
    "DynamicMetrics",
    "HarmonicTone",
    "SimulationReport",
    "StaticLinearity",
    "compute_dynamic_metrics",
    "compute_inl_dnl",
    "simulate_dynamic",
    "simulate_static",
    "write_report",
]
