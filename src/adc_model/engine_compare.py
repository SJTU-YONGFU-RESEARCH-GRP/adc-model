"""Cross-engine metric comparison (Python vs ngspice vs Spectre)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

DEFAULT_ENGINES: tuple[str, ...] = ("python", "ngspice", "spectre")
DEFAULT_REL_TOL = 0.02
DEFAULT_LSB_ATOL = 0.02

MetricName = Literal[
    "max_inl_lsb",
    "max_dnl_lsb",
    "sndr_db",
    "sfdr_db",
    "thd_db",
    "enob_bits",
]

COMPARE_METRICS: tuple[MetricName, ...] = (
    "max_inl_lsb",
    "max_dnl_lsb",
    "sndr_db",
    "sfdr_db",
    "thd_db",
    "enob_bits",
)

LSB_METRICS: frozenset[MetricName] = frozenset({"max_inl_lsb", "max_dnl_lsb"})


@dataclass(frozen=True)
class EngineMetrics:
    """Scalar metrics for one engine run under one test condition."""

    label: str
    engine: str
    max_inl_lsb: float
    max_dnl_lsb: float
    sndr_db: float
    sfdr_db: float
    thd_db: float
    enob_bits: float


@dataclass(frozen=True)
class MetricSpreadRow:
    """Worst-case engine spread for one condition and metric."""

    condition: str
    metric: MetricName
    spread_pct: float
    tol_pct: float
    ok: bool


@dataclass(frozen=True)
class MetricDelta:
    """Relative error of one metric vs the Python reference."""

    condition: str
    engine: str
    metric: MetricName
    reference: float
    actual: float
    abs_delta: float
    rel_delta: float
    within_tol: bool


def metric_value(row: EngineMetrics, metric: MetricName) -> float:
    """Return a scalar metric from an engine metrics row."""
    return float(getattr(row, metric))


def within_relative_tol(
    reference: float,
    actual: float,
    *,
    rtol: float = DEFAULT_REL_TOL,
    atol: float = 0.0,
    lsb_atol: float = DEFAULT_LSB_ATOL,
    is_lsb: bool = False,
) -> bool:
    """Return whether ``actual`` is within tolerance of ``reference``.

    For LSB metrics, when the reference is near zero an absolute tolerance of
    ``lsb_atol`` (default 0.02 LSB) is used. Otherwise relative error must be
    ``<= rtol`` (default 2%).
    """
    if not np.isfinite(reference) and not np.isfinite(actual):
        return True
    if not np.isfinite(reference) or not np.isfinite(actual):
        return False

    abs_delta = abs(actual - reference)
    if is_lsb and abs(reference) < 1e-9:
        return abs_delta <= lsb_atol
    if abs(reference) < atol:
        return abs_delta <= atol
    return abs_delta / abs(reference) <= rtol


def compare_engine_metrics(
    reference: EngineMetrics,
    candidate: EngineMetrics,
    *,
    rtol: float = DEFAULT_REL_TOL,
    lsb_atol: float = DEFAULT_LSB_ATOL,
) -> list[MetricDelta]:
    """Compare one engine row against the Python reference row."""
    deltas: list[MetricDelta] = []
    for metric in COMPARE_METRICS:
        ref_val = metric_value(reference, metric)
        act_val = metric_value(candidate, metric)
        is_lsb = metric in LSB_METRICS
        ok = within_relative_tol(
            ref_val,
            act_val,
            rtol=rtol,
            lsb_atol=lsb_atol,
            is_lsb=is_lsb,
        )
        abs_delta = abs(act_val - ref_val)
        if abs(ref_val) > 1e-12:
            rel_delta = abs_delta / abs(ref_val)
        elif is_lsb and abs(ref_val) < 1e-9:
            rel_delta = abs_delta / lsb_atol if lsb_atol > 0 else abs_delta
        else:
            rel_delta = abs_delta
        deltas.append(
            MetricDelta(
                condition=reference.label,
                engine=candidate.engine,
                metric=metric,
                reference=ref_val,
                actual=act_val,
                abs_delta=abs_delta,
                rel_delta=rel_delta,
                within_tol=ok,
            ),
        )
    return deltas


def check_all_engine_parity(
    metrics_by_label: dict[str, dict[str, EngineMetrics]],
    *,
    reference_engine: str = "python",
    engines: tuple[str, ...] = DEFAULT_ENGINES,
    rtol: float = DEFAULT_REL_TOL,
    lsb_atol: float = DEFAULT_LSB_ATOL,
) -> tuple[bool, list[MetricDelta]]:
    """Check every condition/engine pair against the reference engine."""
    failures: list[MetricDelta] = []
    for label, by_engine in sorted(metrics_by_label.items()):
        ref = by_engine.get(reference_engine)
        if ref is None:
            continue
        for engine in engines:
            if engine == reference_engine:
                continue
            row = by_engine.get(engine)
            if row is None:
                continue
            for delta in compare_engine_metrics(
                ref,
                row,
                rtol=rtol,
                lsb_atol=lsb_atol,
            ):
                if not delta.within_tol:
                    failures.append(delta)
    return len(failures) == 0, failures


def collect_metric_spread_rows(
    metrics_by_label: dict[str, dict[str, EngineMetrics]],
    *,
    reference_engine: str = "python",
    engines: tuple[str, ...] = DEFAULT_ENGINES,
    rtol: float = DEFAULT_REL_TOL,
    lsb_atol: float = DEFAULT_LSB_ATOL,
) -> list[MetricSpreadRow]:
    """Collect per-condition, per-metric spread rows vs the reference engine."""
    rows: list[MetricSpreadRow] = []
    tol_pct = rtol * 100.0
    for label, by_engine in sorted(metrics_by_label.items()):
        ref = by_engine.get(reference_engine)
        if ref is None:
            continue
        for metric in COMPARE_METRICS:
            deltas: list[MetricDelta] = []
            for engine in engines:
                if engine == reference_engine:
                    continue
                row = by_engine.get(engine)
                if row is None:
                    continue
                deltas.extend(
                    compare_engine_metrics(
                        ref,
                        row,
                        rtol=rtol,
                        lsb_atol=lsb_atol,
                    ),
                )
            metric_deltas = [delta for delta in deltas if delta.metric == metric]
            if not metric_deltas:
                continue
            spread_pct = max(delta.rel_delta for delta in metric_deltas) * 100.0
            ok = all(delta.within_tol for delta in metric_deltas)
            rows.append(
                MetricSpreadRow(
                    condition=label,
                    metric=metric,
                    spread_pct=spread_pct,
                    tol_pct=tol_pct,
                    ok=ok,
                ),
            )
    return rows


def collect_all_metric_deltas(
    metrics_by_label: dict[str, dict[str, EngineMetrics]],
    *,
    reference_engine: str = "python",
    engines: tuple[str, ...] = DEFAULT_ENGINES,
    rtol: float = DEFAULT_REL_TOL,
    lsb_atol: float = DEFAULT_LSB_ATOL,
) -> list[MetricDelta]:
    """Collect every metric delta vs the reference engine."""
    deltas: list[MetricDelta] = []
    for label, by_engine in sorted(metrics_by_label.items()):
        ref = by_engine.get(reference_engine)
        if ref is None:
            continue
        for engine in engines:
            if engine == reference_engine:
                continue
            row = by_engine.get(engine)
            if row is None:
                continue
            deltas.extend(
                compare_engine_metrics(
                    ref,
                    row,
                    rtol=rtol,
                    lsb_atol=lsb_atol,
                ),
            )
    return deltas


def format_metric_spread_table(rows: list[MetricSpreadRow]) -> str:
    """Return a markdown table of per-metric engine spread."""
    if not rows:
        return "_No alternate engines found._"

    lines = [
        "| Condition | Metric | Spread % | Tol % | OK |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for row in rows:
        status = "yes" if row.ok else "**no**"
        lines.append(
            f"| `{row.condition}` | `{row.metric}` | "
            f"{row.spread_pct:.2f} | {row.tol_pct:.1f} | {status} |",
        )
    return "\n".join(lines)


def format_metric_delta_table(deltas: list[MetricDelta]) -> str:
    """Return a markdown table of every metric delta vs Python."""
    if not deltas:
        return "_No alternate engines found._"

    lines = [
        "| Condition | Engine | Metric | Python | Actual | Rel Δ % | OK |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for delta in deltas:
        status = "yes" if delta.within_tol else "**no**"
        lines.append(
            f"| `{delta.condition}` | `{delta.engine}` | `{delta.metric}` | "
            f"{delta.reference:.6g} | {delta.actual:.6g} | "
            f"{delta.rel_delta * 100.0:.2f} | {status} |",
        )
    return "\n".join(lines)


def format_engine_metrics_table(
    metrics_by_label: dict[str, dict[str, EngineMetrics]],
    *,
    engines: tuple[str, ...] = DEFAULT_ENGINES,
) -> str:
    """Return a markdown table of raw metrics per engine."""
    lines = [
        "| Condition | Engine | max \\|INL\\| (LSB) | max \\|DNL\\| (LSB) | "
        "SNDR (dB) | SFDR (dB) | THD (dB) | ENOB (bits) |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label, by_engine in sorted(metrics_by_label.items()):
        for engine in engines:
            row = by_engine.get(engine)
            if row is None:
                continue
            lines.append(
                f"| `{label}` | `{engine}` | "
                f"{row.max_inl_lsb:.3f} | {row.max_dnl_lsb:.3f} | "
                f"{row.sndr_db:.2f} | {row.sfdr_db:.2f} | "
                f"{row.thd_db:.2f} | {row.enob_bits:.2f} |",
            )
    return "\n".join(lines)


def format_parity_failures(failures: list[MetricDelta]) -> str:
    """Format parity failure lines for stderr or markdown."""
    lines: list[str] = []
    for delta in failures:
        pct = delta.rel_delta * 100.0
        lines.append(
            f"{delta.condition}/{delta.engine}: {delta.metric} "
            f"ref={delta.reference:.6g} actual={delta.actual:.6g} "
            f"(rel Δ={pct:.2f}%)",
        )
    return "\n".join(lines)
