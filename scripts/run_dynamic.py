#!/usr/bin/env python3
"""Run dynamic spectrum testbench and plot FFT metrics."""

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
from adc_model.dynamic import compute_dynamic_metrics, plot_spectrum
from adc_model.io import read_waveform_csv, write_waveform_csv
from adc_model.model import simulate_dynamic
from adc_model.ngspice_engine import run_dynamic_testbench
from adc_model.simulation_log import (
    archive_veriloga_artifacts,
    prepare_output_dirs,
    run_spectre_testbench,
    write_python_simulation_log,
)
from adc_model.static import decode_codes


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    add_adc_args(parser)
    add_noise_args(parser)
    add_simulator_args(parser)
    parser.add_argument("--num-samples", type=int, default=8192)
    parser.add_argument("--coherent-bin", type=int, default=997)
    parser.add_argument(
        "--fin",
        type=float,
        default=None,
        help="Input tone frequency in Hz. Defaults to a coherent bin.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="CSV waveform from a simulator. If omitted, run the selected engine.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/dynamic"),
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

    csv_path = output_dir / "dynamic_waveform.csv"
    fin_hz = args.fin

    if args.input is not None:
        data = read_waveform_csv(args.input)
        if fin_hz is None:
            fin_hz = args.coherent_bin * cfg.fs_hz / args.num_samples
    elif simulator == "spectre":
        run_spectre_testbench(
            repo_root=repo_root,
            scs_path=repo_root / "testbench/spectre/dynamic_spectrum.scs",
            output_csv=csv_path,
            log_path=log_paths.spectre_dynamic_log,
            fs_hz=cfg.fs_hz,
            max_samples=args.num_samples,
            cfg=cfg,
            noise=noise,
            num_samples=args.num_samples,
            coherent_bin=args.coherent_bin,
        )
        data = read_waveform_csv(csv_path)
        if fin_hz is None:
            fin_hz = args.coherent_bin * cfg.fs_hz / args.num_samples
    elif simulator == "ngspice":
        if fin_hz is None:
            fin_hz = args.coherent_bin * cfg.fs_hz / args.num_samples
        data = run_dynamic_testbench(
            output_dir=output_dir,
            cfg=cfg,
            noise=noise,
            num_samples=args.num_samples,
            fin_hz=fin_hz,
            log_path=log_paths.ngspice_dynamic_log,
        )
    else:
        data = simulate_dynamic(
            cfg,
            num_samples=args.num_samples,
            fin_hz=fin_hz,
            coherent_bin=args.coherent_bin,
            noise=noise,
        )
        write_waveform_csv(csv_path, data)
        fin_hz = float(data["fin_hz"][0])

    codes = decode_codes(data["v_code"], cfg)
    metrics = compute_dynamic_metrics(codes, cfg, fin_hz=fin_hz)
    plot_path = output_dir / "spectrum.svg"
    plot_spectrum(metrics, cfg, plot_path)

    if simulator == "python" and args.input is None:
        write_python_simulation_log(
            log_paths.python_dynamic_log,
            test_name="dynamic_spectrum",
            cfg=cfg,
            noise=noise,
            test_params={
                "num_samples": args.num_samples,
                "coherent_bin": args.coherent_bin,
                "fin_hz": fin_hz,
                "engine": engine,
            },
            results={
                "sndr_db": metrics.sndr_db,
                "sfdr_db": metrics.sfdr_db,
                "thd_db": metrics.thd_db,
                "enob_bits": metrics.enob_bits,
                "harmonics": ", ".join(
                    f"H{tone.order}{'*' if tone.aliased else ''}" for tone in metrics.harmonics
                ),
                "waveform_csv": csv_path.name,
                "plot_svg": plot_path.name,
            },
            veriloga_model=veriloga_model,
        )

    print(f"Engine       : {engine}")
    print(f"Waveform CSV : {csv_path.resolve()}")
    print(f"Spectrum plot: {plot_path.resolve()}")
    print(f"Logs         : {log_paths.logs_dir.resolve()}")
    print(f"Verilog-A    : {log_paths.veriloga_dir.resolve()}")
    print(f"Fin          : {metrics.fin_hz / 1e6:.6f} MHz")
    print(f"SNDR         : {metrics.sndr_db:.2f} dB")
    print(f"SFDR         : {metrics.sfdr_db:.2f} dB")
    print(f"THD          : {metrics.thd_db:.2f} dB")
    print(f"ENOB         : {metrics.enob_bits:.2f} bits")
    if noise.enabled:
        print(
            "Noise        : "
            f"thermal={noise.sigma_thermal_v:.3g} V, "
            f"jitter={noise.jitter_rms_s:.3g} s, "
            f"a3={noise.nonlinearity_a3:.3g}"
        )
    else:
        print("Noise        : disabled (--ideal)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
