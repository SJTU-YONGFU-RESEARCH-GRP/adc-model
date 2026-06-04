#!/usr/bin/env python3
"""Run static INL/DNL testbench and plot results."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from adc_model.cli_helpers import (
    add_adc_args,
    add_noise_args,
    add_simulator_args,
    build_adc_config,
    build_noise_config,
    resolve_engine_label,
)
from adc_model.io import read_waveform_csv, write_waveform_csv
from adc_model.model import simulate_static
from adc_model.ngspice_engine import run_static_testbench
from adc_model.simulation_log import (
    archive_veriloga_artifacts,
    prepare_output_dirs,
    run_spectre_testbench,
    write_python_simulation_log,
)
from adc_model.static import compute_inl_dnl, decode_codes, plot_inl_dnl


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    add_adc_args(parser)
    add_noise_args(parser)
    add_simulator_args(parser)
    parser.add_argument("--samples-per-code", type=int, default=4)
    parser.add_argument(
        "--input",
        type=Path,
        help="CSV waveform from a simulator. If omitted, run the selected engine.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/static"),
        help="Directory for CSV and SVG outputs.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    cfg = build_adc_config(args)
    noise = build_noise_config(args)
    simulator = args.simulator
    engine = resolve_engine_label(simulator)
    log_paths = prepare_output_dirs(output_dir)
    veriloga_model = archive_veriloga_artifacts(repo_root, output_dir)

    csv_path = output_dir / "static_waveform.csv"
    if args.input is not None:
        data = read_waveform_csv(args.input)
    elif simulator == "spectre":
        run_spectre_testbench(
            repo_root=repo_root,
            scs_path=repo_root / "testbench/spectre/static_inl_dnl.scs",
            output_csv=csv_path,
            log_path=log_paths.spectre_static_log,
            fs_hz=cfg.fs_hz,
            cfg=cfg,
            noise=noise,
            samples_per_code=args.samples_per_code,
        )
        data = read_waveform_csv(csv_path)
    elif simulator == "ngspice":
        data = run_static_testbench(
            output_dir=output_dir,
            cfg=cfg,
            noise=noise,
            samples_per_code=args.samples_per_code,
            log_path=log_paths.ngspice_static_log,
        )
    else:
        data = simulate_static(cfg, samples_per_code=args.samples_per_code, noise=noise)
        write_waveform_csv(csv_path, data)

    codes = decode_codes(data["v_code"], cfg)
    method = "histogram" if noise.enabled else "auto"
    result = compute_inl_dnl(data["vin"], codes, cfg, method=method)
    plot_path = output_dir / "inl_dnl.svg"
    plot_inl_dnl(result, cfg, plot_path)

    if simulator == "python" and args.input is None:
        write_python_simulation_log(
            log_paths.python_static_log,
            test_name="static_inl_dnl",
            cfg=cfg,
            noise=noise,
            test_params={
                "samples_per_code": args.samples_per_code,
                "inl_dnl_method": method,
                "engine": engine,
            },
            results={
                "num_samples": len(data["vin"]),
                "max_dnl_lsb": result.max_dnl_lsb,
                "max_inl_lsb": result.max_inl_lsb,
                "waveform_csv": csv_path.name,
                "plot_svg": plot_path.name,
            },
            veriloga_model=veriloga_model,
        )

    print(f"Engine       : {engine}")
    print(f"Waveform CSV : {csv_path.resolve()}")
    print(f"INL/DNL plot : {plot_path.resolve()}")
    print(f"Logs         : {log_paths.logs_dir.resolve()}")
    print(f"Verilog-A    : {log_paths.veriloga_dir.resolve()}")
    print(f"Max |DNL|    : {result.max_dnl_lsb:.3f} LSB")
    print(f"Max |INL|    : {result.max_inl_lsb:.3f} LSB")
    if noise.enabled:
        print(
            "Noise        : "
            f"thermal={noise.sigma_thermal_v:.3g} V, "
            f"jitter={noise.jitter_rms_s:.3g} s, "
            f"dnl_sigma={noise.dnl_sigma_lsb:.3g} LSB"
        )
    else:
        print("Noise        : disabled (--ideal)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
