"""Collect metrics from batch simulation output directories."""

from __future__ import annotations

from pathlib import Path

from adc_model.config import AdcConfig, AdcNoiseConfig
from adc_model.dynamic import compute_dynamic_metrics
from adc_model.engine_compare import DEFAULT_ENGINES, EngineMetrics
from adc_model.io import read_waveform_csv
from adc_model.static import compute_inl_dnl, decode_codes
from adc_model.static_compare import resolve_inl_dnl_method


def condition_label(*, ideal: bool) -> str:
    """Return the batch condition name for ideal vs default-noisy runs."""
    return "ideal" if ideal else "default"


def load_engine_metrics(
    *,
    output_root: Path,
    engine: str,
    cfg: AdcConfig,
    noise: AdcNoiseConfig,
    label: str,
    samples_per_code: int,
    num_samples: int,
    coherent_bin: int,
) -> EngineMetrics | None:
    """Load and analyze metrics for one engine subdirectory under ``output_root``."""
    _ = samples_per_code
    engine_dir = output_root / engine
    static_csv = engine_dir / "static_waveform.csv"
    dynamic_csv = engine_dir / "dynamic_waveform.csv"
    if not static_csv.is_file() or not dynamic_csv.is_file():
        return None

    static_data = read_waveform_csv(static_csv)
    dynamic_data = read_waveform_csv(dynamic_csv)
    static_method = resolve_inl_dnl_method(noise, "auto")
    static_result = compute_inl_dnl(
        static_data["vin"],
        decode_codes(static_data["v_code"], cfg),
        cfg,
        method=static_method,
    )
    fin_hz = coherent_bin * cfg.fs_hz / num_samples
    dynamic_result = compute_dynamic_metrics(
        decode_codes(dynamic_data["v_code"], cfg),
        cfg,
        fin_hz=fin_hz,
    )
    return EngineMetrics(
        label=label,
        engine=engine,
        max_inl_lsb=static_result.max_inl_lsb,
        max_dnl_lsb=static_result.max_dnl_lsb,
        sndr_db=dynamic_result.sndr_db,
        sfdr_db=dynamic_result.sfdr_db,
        thd_db=dynamic_result.thd_db,
        enob_bits=dynamic_result.enob_bits,
    )


def collect_metrics_by_engine(
    output_root: Path,
    cfg: AdcConfig,
    noise: AdcNoiseConfig,
    *,
    label: str,
    engines: tuple[str, ...] = DEFAULT_ENGINES,
    samples_per_code: int = 4,
    num_samples: int = 8192,
    coherent_bin: int = 997,
) -> dict[str, EngineMetrics]:
    """Collect metrics for each engine present under ``output_root``."""
    metrics: dict[str, EngineMetrics] = {}
    for engine in engines:
        row = load_engine_metrics(
            output_root=output_root,
            engine=engine,
            cfg=cfg,
            noise=noise,
            label=label,
            samples_per_code=samples_per_code,
            num_samples=num_samples,
            coherent_bin=coherent_bin,
        )
        if row is not None:
            metrics[engine] = row
    return metrics
