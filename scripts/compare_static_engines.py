#!/usr/bin/env python3
"""Compare static INL/DNL waveforms across Python, ngspice, and Spectre outputs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from adc_model.cli_helpers import add_adc_args, add_noise_args, build_adc_config, build_noise_config
from adc_model.static_compare import (
    analyze_static_waveform,
    expected_hits_per_code,
    format_static_comparison_table,
    resolve_inl_dnl_method,
)

ENGINES = ("python", "ngspice", "spectre")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare static_waveform.csv results under "
            "<output-root>/{python,ngspice,spectre}/."
        ),
    )
    add_adc_args(parser)
    add_noise_args(parser)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("outputs/noise"),
        help="Parent directory containing per-engine subfolders.",
    )
    parser.add_argument(
        "--samples-per-code",
        type=int,
        default=4,
        help="Ramp depth per code (must match the simulation run).",
    )
    parser.add_argument(
        "--inl-dnl-method",
        choices=("auto", "histogram", "transition"),
        default="auto",
        help="INL/DNL algorithm (default: auto, same as run_static.py).",
    )
    parser.add_argument(
        "--engines",
        nargs="+",
        choices=ENGINES,
        default=list(ENGINES),
        help="Engines to include (default: all).",
    )
    parser.add_argument(
        "--check-parity",
        action="store_true",
        help="Exit non-zero when engine metrics diverge from Python beyond tolerances.",
    )
    return parser.parse_args()


def main() -> int:
    """Entry point."""
    args = _parse_args()
    cfg = build_adc_config(args)
    noise = build_noise_config(args)
    inl_dnl_method = resolve_inl_dnl_method(noise, args.inl_dnl_method)
    expected_hits = expected_hits_per_code(
        cfg,
        samples_per_code=args.samples_per_code,
        noise=noise,
    )

    rows = []
    missing: list[str] = []

    for engine in args.engines:
        csv_path = args.output_root / engine / "static_waveform.csv"
        try:
            rows.append(
                analyze_static_waveform(
                    engine,
                    csv_path,
                    cfg,
                    inl_dnl_method=inl_dnl_method,
                ),
            )
        except FileNotFoundError:
            missing.append(str(csv_path))

    if not rows:
        print("No static waveforms found.", file=sys.stderr)
        for path in missing:
            print(f"  missing: {path}", file=sys.stderr)
        return 1

    print(f"Output root: {args.output_root.resolve()}")
    print(f"Noise: {'disabled (--ideal)' if not noise.enabled else 'enabled'}")
    print(format_static_comparison_table(rows, expected_hits=expected_hits))
    print()

    py_row = next((row for row in rows if row.engine == "python"), None)
    if py_row is not None:
        for row in rows:
            if row.engine == "python":
                continue
            dnl_delta = abs(row.max_dnl_lsb - py_row.max_dnl_lsb)
            inl_delta = abs(row.max_inl_lsb - py_row.max_inl_lsb)
            trans_ratio = row.transitions / max(py_row.transitions, 1)
            print(
                f"{row.engine} vs python: "
                f"|DNL| delta={dnl_delta:.3f} LSB, "
                f"|INL| delta={inl_delta:.3f} LSB, "
                f"transitions ratio={trans_ratio:.2f}"
            )

    if missing:
        print("\nSkipped missing files:", file=sys.stderr)
        for path in missing:
            print(f"  {path}", file=sys.stderr)

    if args.check_parity and py_row is not None:
        failures: list[str] = []
        for row in rows:
            if row.engine == "python":
                continue
            dnl_delta = abs(row.max_dnl_lsb - py_row.max_dnl_lsb)
            inl_delta = abs(row.max_inl_lsb - py_row.max_inl_lsb)
            trans_ratio = row.transitions / max(py_row.transitions, 1)
            if row.engine == "ngspice":
                dnl_tol, inl_tol, trans_lo, trans_hi = 0.02, 0.02, 0.98, 1.02
                check_transitions = True
            else:
                dnl_tol, inl_tol, trans_lo, trans_hi = 0.02, 0.02, 0.98, 1.02
                check_transitions = True
            if dnl_delta > dnl_tol:
                failures.append(f"{row.engine}: |DNL| delta {dnl_delta:.3f} > {dnl_tol}")
            if inl_delta > inl_tol:
                failures.append(f"{row.engine}: |INL| delta {inl_delta:.3f} > {inl_tol}")
            if check_transitions and not trans_lo <= trans_ratio <= trans_hi:
                failures.append(
                    f"{row.engine}: transitions ratio {trans_ratio:.2f} not in [{trans_lo}, {trans_hi}]",
                )
        if failures:
            print("\nParity check failed:", file=sys.stderr)
            for msg in failures:
                print(f"  {msg}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
