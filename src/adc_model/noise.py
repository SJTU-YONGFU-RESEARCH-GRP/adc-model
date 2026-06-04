"""ADC noise and nonlinearity models.

Processing order matches ``veriloga/configurable_adc.va``:
  jitter → gain/offset → A2/A3 → thermal → DNL → quantize.
``apply_analog_front_end_at_edges`` applies that chain once per clock edge so
Python/ngspice post-process matches Spectre ``@(cross(clk))`` sampling.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from adc_model.config import AdcConfig, AdcNoiseConfig


def build_dnl_profile(cfg: AdcConfig, noise: AdcNoiseConfig) -> NDArray[np.float64]:
    """Build a fixed per-code DNL threshold offset profile in volts."""
    # Offset seed so DNL draws are independent of per-sample thermal draws.
    rng = np.random.default_rng(noise.noise_seed + 17)
    offsets_lsb = rng.normal(0.0, noise.dnl_sigma_lsb, cfg.num_codes)
    return offsets_lsb * cfg.lsb


def apply_analog_front_end(
    vin: NDArray[np.float64],
    cfg: AdcConfig,
    noise: AdcNoiseConfig,
    *,
    dt: float,
    rng: np.random.Generator,
    dnl_profile: NDArray[np.float64] | None = None,
) -> NDArray[np.float64]:
    """Apply jitter, gain/offset, nonlinearity, and thermal noise."""
    num_samples = len(vin)
    v = vin.astype(np.float64, copy=True)

    if noise.jitter_rms_s > 0.0 and num_samples > 1:
        dv_dt = np.gradient(v, dt)
        jitter_v = noise.jitter_rms_s * dv_dt
        jitter_v *= rng.normal(0.0, 1.0, num_samples)
        v += jitter_v

    v = cfg.gain * v + cfg.offset_v

    vfs = cfg.vrefp - cfg.vrefn
    vcm = 0.5 * (cfg.vrefp + cfg.vrefn)
    if vfs > 0.0 and (noise.nonlinearity_a2 != 0.0 or noise.nonlinearity_a3 != 0.0):
        x = (v - vcm) / vfs
        v += vfs * (noise.nonlinearity_a2 * x**2 + noise.nonlinearity_a3 * x**3)

    if noise.sigma_thermal_v > 0.0:
        v += rng.normal(0.0, noise.sigma_thermal_v, num_samples)

    if dnl_profile is not None and np.any(dnl_profile != 0.0):
        code_est = np.floor((v - cfg.vrefn) / cfg.lsb).astype(np.int64)
        code_est = np.clip(code_est, 0, cfg.max_code - 1)
        v += dnl_profile[code_est]

    return v


def apply_analog_front_end_at_edges(
    vin: NDArray[np.float64],
    edge_idx: NDArray[np.int64],
    cfg: AdcConfig,
    noise: AdcNoiseConfig,
    *,
    dt: float,
    rng: np.random.Generator,
    dnl_profile: NDArray[np.float64] | None = None,
) -> NDArray[np.float64]:
    """Apply the analog front end once per clock edge (Verilog-A sampling).

    Args:
        vin: Input ramp or tone sampled on the simulation time grid.
        edge_idx: Rising-edge indices into ``vin``.
        cfg: ADC configuration.
        noise: Noise / nonlinearity settings.
        dt: Uniform time step between grid points (s).
        rng: Random generator for stochastic terms.
        dnl_profile: Optional per-code DNL threshold offsets (V).

    Returns:
        Front-end voltage at each edge, ready for quantization.
    """
    n_edges = len(edge_idx)
    v_front = np.empty(n_edges, dtype=np.float64)
    vcm = 0.5 * (cfg.vrefp + cfg.vrefn)
    vfs = cfg.vrefp - cfg.vrefn
    vin_prev = vcm

    for k in range(n_edges):
        idx = int(edge_idx[k])
        vin_sample = float(vin[idx])
        # Jitter uses local dv/dt; on dense grids ``dt_sample`` spans multiple UI.
        if k == 0:
            dt_sample = 1.0
        else:
            dt_sample = float((idx - int(edge_idx[k - 1])) * dt)
            if dt_sample <= 0.0:
                dt_sample = dt

        v_eff = vin_sample
        if noise.jitter_rms_s > 0.0:
            dv_dt = (vin_sample - vin_prev) / dt_sample
            v_eff += noise.jitter_rms_s * dv_dt * float(rng.normal())

        v_eff = cfg.gain * v_eff + cfg.offset_v

        if vfs > 0.0 and (noise.nonlinearity_a2 != 0.0 or noise.nonlinearity_a3 != 0.0):
            x_norm = (v_eff - vcm) / vfs
            v_eff += vfs * (
                noise.nonlinearity_a2 * x_norm * x_norm
                + noise.nonlinearity_a3 * x_norm * x_norm * x_norm
            )

        if noise.sigma_thermal_v > 0.0:
            v_eff += noise.sigma_thermal_v * float(rng.normal())

        if dnl_profile is not None and noise.dnl_sigma_lsb > 0.0:
            code_idx = int(np.floor((v_eff - cfg.vrefn) / cfg.lsb))
            code_idx = int(np.clip(code_idx, 0, cfg.max_code - 1))
            v_eff += dnl_profile[code_idx]

        v_front[k] = v_eff
        vin_prev = vin_sample

    return v_front


def apply_post_front_end_noise(
    v_front: NDArray[np.float64],
    cfg: AdcConfig,
    noise: AdcNoiseConfig,
    *,
    rng: np.random.Generator,
    dnl_profile: NDArray[np.float64] | None = None,
) -> NDArray[np.int64]:
    """Apply thermal noise, DNL spread, and quantization after the analog front end.

    This mirrors the final stages of ``apply_analog_front_end`` and is used to
    finish ngspice captures at ``v_nl`` with the same seeded RNG as Python.
    """
    v = v_front.astype(np.float64, copy=True)
    num_samples = len(v)

    if noise.sigma_thermal_v > 0.0:
        v += rng.normal(0.0, noise.sigma_thermal_v, num_samples)

    if dnl_profile is not None and np.any(dnl_profile != 0.0):
        code_est = np.floor((v - cfg.vrefn) / cfg.lsb).astype(np.int64)
        code_est = np.clip(code_est, 0, cfg.max_code - 1)
        v += dnl_profile[code_est]

    return quantize_front_end(v, cfg)


def quantize_front_end(
    v_front: NDArray[np.float64],
    cfg: AdcConfig,
) -> NDArray[np.int64]:
    """Quantize analog front-end samples to integer codes."""
    if np.any(cfg.lsb <= 0.0):
        msg = "LSB must be positive."
        raise ValueError(msg)

    fs_range = cfg.vrefp - cfg.vrefn
    code_real = (v_front - cfg.vrefn) / fs_range * cfg.max_code
    codes = np.floor(code_real + 0.5).astype(np.int64)
    return np.clip(codes, 0, cfg.max_code).astype(np.int64)
