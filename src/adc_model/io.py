"""Waveform I/O and clock-aligned resampling for multi-engine ADC captures.

Python, ngspice, and Spectre may export different time grids (uniform ``1/fs`` vs
dense transients). Functions here pick one sample per ADC clock and align
``v_code`` with Verilog-A ``@(cross(clk))`` behavior.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from numpy.typing import NDArray

WAVEFORM_COLUMNS = ("time", "vin", "clk", "v_code", "code")


def clock_pulse_waveform(
    time: NDArray[np.float64],
    fs_hz: float,
    *,
    duty_cycle: float = 0.5,
) -> NDArray[np.float64]:
    """Return a 50 % duty clock with period ``1/fs_hz`` (matches Spectre ``vsource`` pulse)."""
    period = 1.0 / fs_hz
    phase = np.mod(time, period) / period
    return np.where(phase < duty_cycle, 1.0, 0.0)


def rising_edge_indices(
    clk: NDArray[np.float64],
    *,
    threshold: float = 0.5,
) -> NDArray[np.int64]:
    """Return sample indices of rising clock edges."""
    return np.where((clk[1:] > threshold) & (clk[:-1] <= threshold))[0] + 1


# Dense Spectre/ngspice transients: ``v_code`` updates one UI after ``clk`` rises
# (Verilog-A ``@(cross(clk))`` event vs. held output settling on the fine grid).
_V_CODE_EDGE_OFFSET = 1


def uniform_fs_sample_indices(
    num_samples: int,
    time: NDArray[np.float64],
    fs_hz: float,
) -> NDArray[np.int64]:
    """Return one sample index per ADC clock period on a uniform ``1/fs`` grid.

    When ``median(dt)`` already equals ``1/fs`` (coarse grid), returns ``0..N-1``.
    Otherwise maps ideal sample times ``n/fs`` (s) onto the transient via ``searchsorted``.
    """
    if num_samples <= 0:
        return np.array([], dtype=np.int64)
    if len(time) < 2 or fs_hz <= 0.0:
        return np.arange(min(num_samples, len(time)), dtype=np.int64)
    dt = float(np.median(np.diff(time)))
    period = 1.0 / fs_hz
    if abs(dt - period) <= period * 1.0e-6:
        return np.arange(min(num_samples, len(time)), dtype=np.int64)
    targets = np.arange(num_samples, dtype=np.float64) / fs_hz
    indices = np.searchsorted(time, targets, side="left")
    return np.clip(indices, 0, len(time) - 1).astype(np.int64)


def adc_capture_edge_indices(
    time: NDArray[np.float64],
    fs_hz: float,
    clk: NDArray[np.float64] | None = None,
    *,
    min_edges: int | None = None,
) -> NDArray[np.int64]:
    """Return indices where the ADC samples (rising ``clk`` or one per ``1/fs``).

    Clock alignment:
      - **Coarse grid** (``median(dt) ≈ 1/fs``): sample index ``n`` at ``t = n/fs``
        (Python model, ngspice with ``maxstep = 1/fs``).
      - **Dense grid** (``maxstep < 1/fs``): rising-edge indices from ``clk``; index 0
        is prepended so the first conversion is included.

    Args:
        time: Simulation time stamps (s).
        fs_hz: ADC sample rate (Hz).
        clk: Optional clock waveform (0/1); synthesized from ``time`` if absent on dense grids.
        min_edges: Minimum edges required before trusting ``clk`` detection.

    Returns:
        Integer indices into ``time`` / ``vin`` for each conversion instant.
    """
    num_samples = len(time)
    if min_edges is None:
        min_edges = max(4, num_samples // 8)
    if num_samples < 2 or fs_hz <= 0.0:
        return np.arange(num_samples, dtype=np.int64)

    # Coarse grid: one point per clock period (Python model, ngspice at fs).
    dt = float(np.median(np.diff(time)))
    period = 1.0 / fs_hz
    if abs(dt - period) <= period * 1.0e-6:
        return uniform_fs_sample_indices(num_samples, time, fs_hz)

    # Dense grid: follow simulated rising edges (Spectre maxstep < 1/fs).
    if clk is not None and len(clk) == num_samples:
        edges = rising_edge_indices(clk)
        if len(edges) >= min_edges:
            return np.unique(np.concatenate(([0], edges)).astype(np.int64))

    # Fallback when ``clk`` is missing: synthesize 1/fs edges from time stamps.
    ideal_clk = clock_pulse_waveform(time, fs_hz)
    return np.unique(
        np.concatenate(([0], rising_edge_indices(ideal_clk))).astype(np.int64)
    )


def static_capture_edge_indices(
    num_samples: int,
    clk: NDArray[np.float64] | None = None,
    *,
    samples_per_code: int = 1,
    time: NDArray[np.float64] | None = None,
    fs_hz: float | None = None,
    min_edges: int | None = None,
) -> NDArray[np.int64]:
    """Return sample indices where the static ramp ADC samples.

    Matches ``configurable_adc.va`` ``@(cross(clk))``: one conversion per clock
    period on the uniform grid ``t = n/fs`` for ``n = 0 .. num_samples-1``.
    Ramp depth is ``num_codes * samples_per_code`` clock cycles; ``samples_per_code``
    sets dwell length for histogram averaging (API parity with testbench scripts).

    On dense transients (Spectre/ngspice ``maxstep < 1/fs``), pick the time stamp
    nearest each ideal ``n/fs`` via ``searchsorted`` rather than the first N dense points.

    Args:
        num_samples: Number of ADC decisions to export (``num_codes * samples_per_code``).
        time: Simulation time array (s); required for dense-grid alignment.
        fs_hz: Sample rate (Hz).

    Returns:
        Indices into ``vin`` where the front end is evaluated for static capture.
    """
    _ = (clk, samples_per_code, min_edges)
    if time is None or fs_hz is None or fs_hz <= 0.0 or num_samples <= 0:
        return np.arange(max(num_samples, 0), dtype=np.int64)
    if len(time) < 2:
        return np.clip(np.arange(num_samples, dtype=np.int64), 0, len(time) - 1)

    dt = float(np.median(np.diff(time)))
    period = 1.0 / fs_hz
    if abs(dt - period) <= period * 1.0e-6:
        return np.arange(min(num_samples, len(time)), dtype=np.int64)

    targets = np.arange(num_samples, dtype=np.float64) / fs_hz
    edge_idx = np.searchsorted(time, targets, side="left")
    return np.clip(edge_idx, 0, len(time) - 1).astype(np.int64)


def prepare_edge_aligned_waveform(
    waveform: dict[str, NDArray[np.float64]],
    fs_hz: float,
    *,
    max_samples: int | None = None,
) -> dict[str, NDArray[np.float64]]:
    """Downsample a dense transient to one ADC sample per ``1/fs`` clock period.

    Matches Spectre ``@(cross(clk))`` sampling: on dense grids, sample at
    ``rising_edge(clk) + _V_CODE_EDGE_OFFSET`` so ``v_code`` aligns with the held
    output after the edge. Coarse ``dt = 1/fs`` waveforms pass through unchanged
    (optionally truncated to ``max_samples`` via :func:`uniform_fs_sample_indices`).

    Args:
        waveform: Must include ``time``; dense paths require ``clk``.
        fs_hz: ADC sample rate (Hz).
        max_samples: Cap on exported rows after downsampling.
    """
    time = waveform["time"]
    num_samples = len(time)
    if num_samples < 2 or fs_hz <= 0.0:
        return waveform

    dt = float(np.median(np.diff(time)))
    period = 1.0 / fs_hz
    if abs(dt - period) <= period * 1.0e-6:
        sample_idx = uniform_fs_sample_indices(num_samples, time, fs_hz)
    else:
        if "clk" not in waveform:
            msg = "Dense waveform must include clk for edge-aligned downsampling."
            raise ValueError(msg)
        edge_idx = rising_edge_indices(waveform["clk"])
        # VA updates ``v_code`` on ``@(cross(clk))`` after the edge settles.
        sample_idx = edge_idx + _V_CODE_EDGE_OFFSET
        sample_idx = sample_idx[sample_idx < num_samples]

    if max_samples is not None:
        sample_idx = sample_idx[:max_samples]

    if len(sample_idx) == 0:
        return waveform

    return {name: values[sample_idx] for name, values in waveform.items()}


def write_waveform_csv(path: Path, data: dict[str, NDArray[np.float64]]) -> None:
    """Write a simulation waveform dictionary to CSV.

    Args:
        path: Destination CSV path.
        data: Mapping that includes at least ``time``, ``vin``, ``clk``, and ``v_code``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [name for name in WAVEFORM_COLUMNS if name in data]
    matrix = np.column_stack([data[name] for name in columns])
    header = ",".join(columns)
    np.savetxt(path, matrix, delimiter=",", header=header, comments="")


def read_waveform_csv(path: Path) -> dict[str, NDArray[np.float64]]:
    """Read a simulation waveform CSV exported by the testbench.

    Args:
        path: Source CSV path.

    Returns:
        Dictionary of waveform arrays keyed by column name.
    """
    table = np.genfromtxt(path, delimiter=",", names=True)
    return {name: np.asarray(table[name], dtype=np.float64) for name in table.dtype.names}


def read_waveform_wrdata(
    path: Path,
    *,
    analog_signal: str = "v_code",
) -> dict[str, NDArray[np.float64]]:
    """Read an ngspice ``wrdata`` file written with ``wr_singlescale``.

    Args:
        path: Source wrdata path with columns ``time``, ``vin``, optional ``clk``,
            and either ``v_code`` or ``v_th``.
        analog_signal: Name of the final analog probe column (``v_code`` or ``v_th``).

    Returns:
        Waveform dictionary keyed by signal name.
    """
    table = np.loadtxt(path)
    if table.ndim == 1:
        table = table.reshape(1, -1)
    if table.shape[1] < 3:
        msg = f"Expected at least 3 columns in wrdata file, got {table.shape[1]}."
        raise ValueError(msg)

    time = table[:, 0]
    vin = table[:, 1]
    result: dict[str, NDArray[np.float64]] = {"time": time, "vin": vin}
    if table.shape[1] >= 4:
        result["clk"] = table[:, 2]
        result[analog_signal] = table[:, 3]
    else:
        result[analog_signal] = table[:, 2]
        # Older wrdata without ``clk``: reconstruct a square wave from sample spacing.
        if len(time) > 1:
            dt = float(np.median(np.diff(time)))
            phase = np.round(time / dt).astype(np.int64)
            result["clk"] = np.where(phase % 2 == 0, 0.0, 1.0)
        else:
            result["clk"] = np.zeros_like(time)
    return result


def resample_uniform_sample_rate(
    waveform: dict[str, NDArray[np.float64]],
    fs_hz: float,
) -> dict[str, NDArray[np.float64]]:
    """Keep one transient sample per ADC clock period on a uniform time grid."""
    dt = 1.0 / fs_hz
    time = waveform["time"]
    if len(time) < 2 or fs_hz <= 0.0:
        return waveform

    n_samples = int(np.floor((time[-1] - time[0]) / dt + 0.5)) + 1
    if n_samples < 2:
        return waveform

    sample_times = time[0] + np.arange(n_samples, dtype=np.float64) * dt
    indices = np.array([int(np.argmin(np.abs(time - target))) for target in sample_times])
    resampled = {name: values[indices] for name, values in waveform.items()}
    resampled["time"] = sample_times
    return resampled

