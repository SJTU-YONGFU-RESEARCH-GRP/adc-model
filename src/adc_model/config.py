"""ADC configuration dataclasses.

``AdcConfig`` holds gain/offset mismatch knobs shared by Python, Spectre, and
ngspice. ``AdcNoiseConfig`` mirrors the ``parameters`` block in the VA testbenches;
``enabled`` is False when ``--ideal`` is passed on the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AdcConfig:
    """Static configuration for the configurable ADC testbench.

    Fields (shared by Python, Spectre, ngspice):
        bits: ADC resolution; full-scale code is ``2**bits - 1``.
        vrefp: Positive reference (V).
        vrefn: Negative reference (V); full span ``vrefp - vrefn``.
        gain: Input gain applied before quantization (dimensionless).
        offset_v: Input-referred DC offset added after gain (V).
        fs_hz: Sample / clock rate (Hz); simulation time step is ``1/fs_hz`` (s).

    Derived:
        lsb: ``(vrefp - vrefn) / max_code`` (V/LSB).
        max_code: ``2**bits - 1``.
        num_codes: ``max_code + 1`` quantizer levels (0 .. max_code).
    """

    bits: int = 10
    vrefp: float = 1.0
    vrefn: float = 0.0
    gain: float = 1.0
    offset_v: float = 0.0
    fs_hz: float = 1.0e6

    @property
    def max_code(self) -> int:
        """Return full-scale digital code."""
        return (1 << self.bits) - 1

    @property
    def lsb(self) -> float:
        """Return ideal LSB size in volts."""
        return (self.vrefp - self.vrefn) / self.max_code

    @property
    def num_codes(self) -> int:
        """Return number of quantizer levels (0 .. max_code inclusive)."""
        return self.max_code + 1


@dataclass(frozen=True)
class AdcNoiseConfig:
    """Input-referred noise and nonlinearity contributions.

    Mirrors the Verilog-A ``parameters`` block. CLI ``--ideal`` sets all magnitudes
    to zero so :attr:`enabled` is False.

    Fields:
        sigma_thermal_v: RMS thermal noise voltage (V), added before quantize.
        jitter_rms_s: RMS aperture jitter (s); converted to volts via ``dv/dt``.
        nonlinearity_a2: Quadratic coefficient on normalized input ``x = (v-Vcm)/Vfs``.
        nonlinearity_a3: Cubic coefficient on ``x`` (same normalization).
        dnl_sigma_lsb: RMS per-code threshold spread (LSB); fixed profile per run.
        noise_seed: Seed for thermal/jitter RNG; DNL profile uses ``noise_seed + 17``.
    """

    sigma_thermal_v: float = 0.0
    jitter_rms_s: float = 0.0
    nonlinearity_a2: float = 0.0
    nonlinearity_a3: float = 0.0
    dnl_sigma_lsb: float = 0.0
    noise_seed: int = 1

    @property
    def enabled(self) -> bool:
        """Return True if any non-ideal mechanism is active."""
        return (
            self.sigma_thermal_v > 0.0
            or self.jitter_rms_s > 0.0
            or self.nonlinearity_a2 != 0.0
            or self.nonlinearity_a3 != 0.0
            or self.dnl_sigma_lsb > 0.0
        )
