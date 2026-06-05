#!/usr/bin/env python3
"""Compare Python, ngspice, and Spectre metrics under an output root."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from adc_model.batch_metrics import collect_metrics_by_engine, condition_label
from adc_model.cli_helpers import add_adc_args, add_noise_args, build_adc_config, build_noise_config
from adc_model.engine_compare import (
    DEFAULT_ENGINES,
    DEFAULT_REL_TOL,
    EngineMetrics,
    MetricDelta,
    MetricSpreadRow,
    check_all_engine_parity,
    collect_all_metric_deltas,
    collect_metric_spread_rows,
    format_engine_metrics_table,
    format_metric_delta_table,
    format_metric_spread_table,
    format_parity_failures,
)

BATCH_SUMMARY_FILENAME = "SUMMARY.md"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare static/dynamic metrics across engine output folders under "
            "<output-root>/{python,ngspice,spectre}/."
        ),
    )
    add_adc_args(parser)
    add_noise_args(parser)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("outputs"),
        help="Parent directory containing per-engine subfolders.",
    )
    parser.add_argument(
        "--engines",
        nargs="+",
        choices=DEFAULT_ENGINES,
        default=list(DEFAULT_ENGINES),
        help="Engines to include (default: all found).",
    )
    parser.add_argument(
        "--samples-per-code",
        type=int,
        default=4,
        help="Static ramp depth per code (must match the simulation run).",
    )
    parser.add_argument(
        "--num-samples",
        type=int,
        default=8192,
        help="Dynamic FFT record length (must match the simulation run).",
    )
    parser.add_argument(
        "--coherent-bin",
        type=int,
        default=997,
        help="Coherent FFT bin used for dynamic analysis.",
    )
    parser.add_argument(
        "--rtol",
        type=float,
        default=DEFAULT_REL_TOL,
        help=f"Relative tolerance vs Python reference (default: {DEFAULT_REL_TOL}).",
    )
    parser.add_argument(
        "--check-parity",
        action="store_true",
        help="Exit non-zero when any metric exceeds the relative tolerance.",
    )
    parser.add_argument(
        "--write-summary",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=f"Write {BATCH_SUMMARY_FILENAME} under --output-root (default: on).",
    )
    return parser.parse_args()


def build_batch_summary_markdown(
    *,
    output_root: Path,
    metrics_by_label: dict[str, dict[str, EngineMetrics]],
    spread_rows: list[MetricSpreadRow],
    metric_deltas: list[MetricDelta],
    rtol: float,
    generated_at: datetime,
    all_ok: bool,
    engines_present: int,
    has_python_reference: bool,
) -> str:
    """Build the cross-engine batch summary markdown document."""
    tol_pct = rtol * 100.0
    lines = [
        "# ADC Batch Simulation Summary",
        "",
        f"Generated: {generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"Output root: `{output_root.resolve()}`",
        "Reference engine: `python`",
        f"Relative tolerance: {tol_pct:.1f}%",
        "",
        "## Engine metrics",
        "",
        format_engine_metrics_table(metrics_by_label),
        "",
        "## Per-engine deltas vs python",
        "",
        format_metric_delta_table(metric_deltas),
        "",
        "## Metric spread",
        "",
        format_metric_spread_table(spread_rows),
        "",
        "Spread % is the worst relative delta vs Python among ngspice and Spectre.",
        "LSB metrics with a near-zero reference use a 0.02 LSB absolute band.",
        "",
    ]
    if has_python_reference and engines_present > 1:
        verdict = "yes" if all_ok else "no"
        lines.append(f"All metrics within {tol_pct:.1f}% tolerance vs python: {verdict}")
    else:
        lines.append(
            "Cross-engine comparison skipped (need python plus at least one other engine).",
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    """Entry point."""
    args = _parse_args()
    cfg = build_adc_config(args)
    noise = build_noise_config(args)
    label = condition_label(ideal=args.ideal)
    engines = tuple(args.engines)

    metrics = collect_metrics_by_engine(
        args.output_root,
        cfg,
        noise,
        label=label,
        engines=engines,
        samples_per_code=args.samples_per_code,
        num_samples=args.num_samples,
        coherent_bin=args.coherent_bin,
    )
    if not metrics:
        print(f"No engine outputs found under {args.output_root.resolve()}", file=sys.stderr)
        return 1

    if "python" not in metrics:
        print(
            "warning: Python reference outputs missing; spread table requires "
            "`python` under the output root.",
            file=sys.stderr,
        )

    metrics_by_label = {label: metrics}
    metric_deltas = collect_all_metric_deltas(
        metrics_by_label,
        engines=engines,
        rtol=args.rtol,
    )
    spread_rows = collect_metric_spread_rows(
        metrics_by_label,
        engines=engines,
        rtol=args.rtol,
    )
    all_ok, failures = check_all_engine_parity(
        metrics_by_label,
        engines=engines,
        rtol=args.rtol,
    )

    generated_at = datetime.now(tz=UTC)
    summary_text = build_batch_summary_markdown(
        output_root=args.output_root,
        metrics_by_label=metrics_by_label,
        spread_rows=spread_rows,
        metric_deltas=metric_deltas,
        rtol=args.rtol,
        generated_at=generated_at,
        all_ok=all_ok,
        engines_present=len(metrics),
        has_python_reference="python" in metrics,
    )

    print(f"Collecting metrics from {args.output_root.resolve()} ...")
    print()
    print(summary_text)

    if args.write_summary:
        summary_path = args.output_root / BATCH_SUMMARY_FILENAME
        summary_path.write_text(summary_text, encoding="utf-8")
        print(f"Wrote {summary_path.resolve()}")

    if failures:
        print("\nParity failures:", file=sys.stderr)
        print(format_parity_failures(failures), file=sys.stderr)

    if args.check_parity and not all_ok:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
