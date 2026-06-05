"""Configurable ADC behavioral model and testbench analysis."""

from adc_model.config import AdcConfig, AdcNoiseConfig
from adc_model.dynamic import DynamicMetrics, HarmonicTone, compute_dynamic_metrics
from adc_model.model import simulate_dynamic, simulate_static
from adc_model.report import SUMMARY_FILENAME, SimulationReport, write_report, write_simulation_summary
from adc_model.static import StaticLinearity, compute_inl_dnl

__all__ = [
    "AdcConfig",
    "AdcNoiseConfig",
    "DynamicMetrics",
    "HarmonicTone",
    "SUMMARY_FILENAME",
    "SimulationReport",
    "StaticLinearity",
    "compute_dynamic_metrics",
    "compute_inl_dnl",
    "simulate_dynamic",
    "simulate_static",
    "write_report",
    "write_simulation_summary",
]
