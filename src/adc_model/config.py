"""ADC configuration dataclasses.

``AdcConfig`` holds gain/offset mismatch knobs shared by Python, Spectre, and
ngspice. ``AdcNoiseConfig`` mirrors the ``parameters`` block in the VA testbenches;
``enabled`` is False when ``--ideal`` is passed on the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AdcConfig:
    """Static configuration for the configurable ADC testbench."""

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
    """Input-referred noise and nonlinearity contributions."""

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
