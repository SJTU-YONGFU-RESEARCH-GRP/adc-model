#!/usr/bin/env python3
"""Run static and dynamic ADC simulations, analysis, and SUMMARY.md generation."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
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
from adc_model.model import simulate_dynamic, simulate_static
from adc_model.ngspice_engine import run_dynamic_testbench, run_static_testbench
from adc_model.report import (
    DynamicTestConfig,
    SUMMARY_FILENAME,
    StaticTestConfig,
    write_simulation_summary,
)
from adc_model.simulation_log import (
    archive_veriloga_artifacts,
    prepare_output_dirs,
    run_spectre_testbench,
    write_python_simulation_log,
)
from adc_model.static import compute_inl_dnl, decode_codes, plot_inl_dnl


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run static INL/DNL and dynamic FFT simulations, plot results, "
            "archive logs, and write SUMMARY.md."
        ),
    )
    add_adc_args(parser)
    add_noise_args(parser)
    add_simulator_args(parser)
    parser.add_argument("--samples-per-code", type=int, default=4)
    parser.add_argument("--num-samples", type=int, default=8192)
    parser.add_argument("--coherent-bin", type=int, default=997)
    parser.add_argument(
        "--fin",
        type=float,
        default=None,
        help="Input tone frequency in Hz. Defaults to a coherent bin.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/simulation"),
        help="Directory for waveforms, figures, logs, and SUMMARY.md.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help=f"Summary path (default: <output-dir>/{SUMMARY_FILENAME}).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.report or (output_dir / SUMMARY_FILENAME)

    cfg = build_adc_config(args)
    noise = build_noise_config(args)
    simulator = args.simulator
    engine = resolve_engine_label(simulator)
    log_paths = prepare_output_dirs(output_dir)
    veriloga_model = archive_veriloga_artifacts(repo_root, output_dir)

    static_csv = output_dir / "static_waveform.csv"
    dynamic_csv = output_dir / "dynamic_waveform.csv"
    inl_plot = output_dir / "inl_dnl.svg"
    spectrum_plot = output_dir / "spectrum.svg"

    if simulator == "spectre":
        run_spectre_testbench(
            repo_root=repo_root,
            scs_path=repo_root / "testbench/spectre/static_inl_dnl.scs",
            output_csv=static_csv,
            log_path=log_paths.spectre_static_log,
            fs_hz=cfg.fs_hz,
            cfg=cfg,
            noise=noise,
            samples_per_code=args.samples_per_code,
        )
        static_data = read_waveform_csv(static_csv)
    elif simulator == "ngspice":
        static_data = run_static_testbench(
            output_dir=output_dir,
            cfg=cfg,
            noise=noise,
            samples_per_code=args.samples_per_code,
            log_path=log_paths.ngspice_static_log,
        )
    else:
        static_data = simulate_static(cfg, samples_per_code=args.samples_per_code, noise=noise)
        write_waveform_csv(static_csv, static_data)

    static_codes = decode_codes(static_data["v_code"], cfg)
    static_method = "histogram" if noise.enabled else "auto"
    static_result = compute_inl_dnl(static_data["vin"], static_codes, cfg, method=static_method)
    plot_inl_dnl(static_result, cfg, inl_plot)

    if simulator == "python":
        write_python_simulation_log(
            log_paths.python_static_log,
            test_name="static_inl_dnl",
            cfg=cfg,
            noise=noise,
            test_params={
                "samples_per_code": args.samples_per_code,
                "inl_dnl_method": static_method,
            },
            results={
                "num_samples": len(static_data["vin"]),
                "max_dnl_lsb": static_result.max_dnl_lsb,
                "max_inl_lsb": static_result.max_inl_lsb,
                "waveform_csv": static_csv.name,
                "plot_svg": inl_plot.name,
            },
            veriloga_model=veriloga_model,
        )

    fin_hz = args.fin
    if simulator == "spectre":
        run_spectre_testbench(
            repo_root=repo_root,
            scs_path=repo_root / "testbench/spectre/dynamic_spectrum.scs",
            output_csv=dynamic_csv,
            log_path=log_paths.spectre_dynamic_log,
            fs_hz=cfg.fs_hz,
            max_samples=args.num_samples,
            cfg=cfg,
            noise=noise,
            num_samples=args.num_samples,
            coherent_bin=args.coherent_bin,
        )
        dynamic_data = read_waveform_csv(dynamic_csv)
        if fin_hz is None:
            fin_hz = args.coherent_bin * cfg.fs_hz / args.num_samples
    elif simulator == "ngspice":
        if fin_hz is None:
            fin_hz = args.coherent_bin * cfg.fs_hz / args.num_samples
        dynamic_data = run_dynamic_testbench(
            output_dir=output_dir,
            cfg=cfg,
            noise=noise,
            num_samples=args.num_samples,
            fin_hz=fin_hz,
            log_path=log_paths.ngspice_dynamic_log,
        )
    else:
        dynamic_data = simulate_dynamic(
            cfg,
            num_samples=args.num_samples,
            fin_hz=fin_hz,
            coherent_bin=args.coherent_bin,
            noise=noise,
        )
        write_waveform_csv(dynamic_csv, dynamic_data)
        fin_hz = float(dynamic_data["fin_hz"][0])

    dynamic_codes = decode_codes(dynamic_data["v_code"], cfg)
    dynamic_result = compute_dynamic_metrics(dynamic_codes, cfg, fin_hz=fin_hz)
    plot_spectrum(dynamic_result, cfg, spectrum_plot)

    if simulator == "python":
        write_python_simulation_log(
            log_paths.python_dynamic_log,
            test_name="dynamic_spectrum",
            cfg=cfg,
            noise=noise,
            test_params={
                "num_samples": args.num_samples,
                "coherent_bin": args.coherent_bin,
                "fin_hz": fin_hz,
            },
            results={
                "sndr_db": dynamic_result.sndr_db,
                "sfdr_db": dynamic_result.sfdr_db,
                "thd_db": dynamic_result.thd_db,
                "enob_bits": dynamic_result.enob_bits,
                "harmonics": ", ".join(
                    f"H{tone.order}{'*' if tone.aliased else ''}" for tone in dynamic_result.harmonics
                ),
                "waveform_csv": dynamic_csv.name,
                "plot_svg": spectrum_plot.name,
            },
            veriloga_model=veriloga_model,
        )

    written_report = write_simulation_summary(
        output_dir=output_dir,
        adc=cfg,
        noise=noise,
        static_cfg=StaticTestConfig(
            samples_per_code=args.samples_per_code,
            inl_dnl_method=static_method,
            engine=engine,
        ),
        dynamic_cfg=DynamicTestConfig(
            num_samples=args.num_samples,
            coherent_bin=args.coherent_bin,
            fin_hz=fin_hz,
            engine=engine,
        ),
        static_result=static_result,
        dynamic_result=dynamic_result,
        simulator=simulator,
        log_paths=log_paths,
        veriloga_model=veriloga_model,
        summary_path=report_path,
        generated_at=datetime.now(tz=timezone.utc),
    )

    print(f"Summary      : {written_report}")
    print(f"Engine       : {engine}")
    print(f"Logs         : {log_paths.logs_dir.resolve()}")
    print(f"Verilog-A    : {log_paths.veriloga_dir.resolve()}")
    if args.simulator == "ngspice":
        print(f"ngspice TB   : {log_paths.ngspice_dir.resolve()}")
    print(f"INL/DNL plot : {inl_plot.resolve()}")
    print(f"Spectrum plot: {spectrum_plot.resolve()}")
    print(f"Max |DNL|    : {static_result.max_dnl_lsb:.3f} LSB")
    print(f"Max |INL|    : {static_result.max_inl_lsb:.3f} LSB")
    print(f"SNDR         : {dynamic_result.sndr_db:.2f} dB")
    print(f"ENOB         : {dynamic_result.enob_bits:.2f} bits")
    return 0


if __name__ == "__main__":
    sys.exit(main())
