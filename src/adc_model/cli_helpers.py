"""Shared CLI helpers for testbench scripts.

``build_noise_config`` maps ``--ideal`` to zeroed noise parameters so Python,
ngspice, and Spectre runs share one configuration object.
"""

from __future__ import annotations

import argparse

from adc_model.config import AdcConfig, AdcNoiseConfig


def add_adc_args(parser: argparse.ArgumentParser) -> None:
    """Register ADC configuration arguments."""
    parser.add_argument("--bits", type=int, default=10)
    parser.add_argument("--vrefp", type=float, default=1.0)
    parser.add_argument("--vrefn", type=float, default=0.0)
    parser.add_argument("--gain", type=float, default=1.01)
    parser.add_argument("--offset-v", type=float, default=5e-3)
    parser.add_argument("--fs", type=float, default=1.0e6)


def add_noise_args(parser: argparse.ArgumentParser) -> None:
    """Register noise / nonlinearity arguments."""
    parser.add_argument(
        "--ideal",
        action="store_true",
        help="Disable all noise and nonlinearity (quantizer-limited only).",
    )
    parser.add_argument(
        "--sigma-thermal-v",
        type=float,
        default=250e-6,
        help="Input-referred RMS white noise in volts (default: 250 uV).",
    )
    parser.add_argument(
        "--jitter-rms-s",
        type=float,
        default=500e-15,
        help="Aperture jitter RMS in seconds (default: 500 fs).",
    )
    parser.add_argument(
        "--nonlinearity-a2",
        type=float,
        default=0.0,
        help="Second-order nonlinearity coefficient vs full-scale.",
    )
    parser.add_argument(
        "--nonlinearity-a3",
        type=float,
        default=-0.002,
        help="Third-order nonlinearity coefficient vs full-scale.",
    )
    parser.add_argument(
        "--dnl-sigma-lsb",
        type=float,
        default=0.08,
        help="Per-code comparator threshold spread in LSB RMS.",
    )
    parser.add_argument("--noise-seed", type=int, default=1)


def add_simulator_args(parser: argparse.ArgumentParser) -> None:
    """Register mutually exclusive simulator selection arguments."""
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--simulator",
        choices=("python", "spectre", "ngspice"),
        default="python",
        help="Simulation engine (default: python).",
    )
    group.add_argument(
        "--spectre",
        action="store_const",
        const="spectre",
        dest="simulator",
        help="Use Cadence Spectre (alias for --simulator spectre).",
    )
    group.add_argument(
        "--ngspice",
        action="store_const",
        const="ngspice",
        dest="simulator",
        help="Use ngspice behavioral netlists (alias for --simulator ngspice).",
    )


def resolve_engine_label(simulator: str) -> str:
    """Return a human-readable simulator label."""
    labels = {
        "python": "Python behavioral model",
        "spectre": "Cadence Spectre",
        "ngspice": "ngspice behavioral netlist",
    }
    return labels.get(simulator, simulator)


def build_adc_config(args: argparse.Namespace) -> AdcConfig:
    """Build ``AdcConfig`` from parsed CLI arguments."""
    return AdcConfig(
        bits=args.bits,
        vrefp=args.vrefp,
        vrefn=args.vrefn,
        gain=args.gain,
        offset_v=args.offset_v,
        fs_hz=args.fs,
    )


def build_noise_config(args: argparse.Namespace) -> AdcNoiseConfig:
    """Build ``AdcNoiseConfig`` from parsed CLI arguments."""
    if args.ideal:
        return AdcNoiseConfig()
    return AdcNoiseConfig(
        sigma_thermal_v=args.sigma_thermal_v,
        jitter_rms_s=args.jitter_rms_s,
        nonlinearity_a2=args.nonlinearity_a2,
        nonlinearity_a3=args.nonlinearity_a3,
        dnl_sigma_lsb=args.dnl_sigma_lsb,
        noise_seed=args.noise_seed,
    )
