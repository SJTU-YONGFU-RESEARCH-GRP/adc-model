# ADC Simulation Summary

Generated: 2026-06-05 18:06:40 UTC

Behavioral simulation of `configurable_adc` with static INL/DNL and dynamic FFT analysis.

## Input Configuration

### ADC Core

| Parameter | Value |
| --- | --- |
| Resolution | 10 bits |
| Full-scale range | 0 V to 1 V |
| Ideal LSB | 977.517 uV |
| Sample rate | 1 MHz |
| Gain | 1.01 |
| Offset | 5 mV |

### Noise and Nonlinearity

| Parameter | Value |
| --- | --- |
| Thermal noise (RMS) | 250 uV |
| Aperture jitter (RMS) | 500 fs |
| Nonlinearity A2 | 0 |
| Nonlinearity A3 | -0.002 |
| DNL spread (RMS) | 0.08 LSB |
| Random seed | 1 |

### Static Testbench

| Parameter | Value |
| --- | --- |
| Engine | Cadence Spectre |
| Stimulus | Slow ramp across full input range |
| Samples per code | 4 |
| INL/DNL method | histogram |
| Waveform CSV | static_waveform.csv |

### Dynamic Testbench

| Parameter | Value |
| --- | --- |
| Engine | Cadence Spectre |
| Stimulus | Coherent full-scale sine |
| Capture length | 8192 samples |
| Coherent bin | 997 |
| Input tone | 121.704 kHz |
| Waveform CSV | dynamic_waveform.csv |

## Static Linearity Results

| Metric | Value |
| --- | --- |
| Max DNL (abs) | 1.000 LSB |
| Max INL (abs) | 4.374 LSB |

![INL/DNL plot](inl_dnl.svg)

## Dynamic Spectrum Results

| Metric | Value |
| --- | --- |
| Input tone | 121.704 kHz |
| SNDR | 59.09 dB |
| SFDR | 85.48 dB |
| THD | 78.77 dB |
| ENOB | 9.52 bits |

### Identified Harmonics

| Tone | Frequency | Magnitude |
| --- | --- | --- |
| Fin | 121.704 kHz | 77.91 dBFS |
| H2 | 243.164 kHz | -15.95 dBFS |
| H3 | 365.112 kHz | -1.49 dBFS |
| H4 | 486.572 kHz | -13.85 dBFS |
| H5* | 391.479 kHz | -15.81 dBFS |
| H6* | 269.897 kHz | -17.66 dBFS |

Aliased harmonics are marked with `*`.

![Dynamic spectrum](spectrum.svg)

## Output Files

| Artifact | Path |
| --- | --- |
| Static waveform | static_waveform.csv |
| INL/DNL figure | inl_dnl.svg |
| Dynamic waveform | dynamic_waveform.csv |
| Spectrum figure | spectrum.svg |
| Verilog-A model snapshot | veriloga/configurable_adc.va |
| Simulation log | logs/spectre_static.log |
| Simulation log | logs/spectre_dynamic.log |
