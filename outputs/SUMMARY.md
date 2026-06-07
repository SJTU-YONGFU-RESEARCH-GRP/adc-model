# ADC Batch Simulation Summary

Generated: 2026-06-07 15:19:36 UTC
Output root: `/home/yongfu/proj/circuit-calibration/adc-calibration/model/adc-model/outputs`
Reference engine: `python`
Relative tolerance: 2.0%

## Engine metrics

| Condition | Engine | max \|INL\| (LSB) | max \|DNL\| (LSB) | SNDR (dB) | SFDR (dB) | THD (dB) | ENOB (bits) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `default` | `python` | 4.441 | 1.000 | 58.92 | 85.66 | 79.85 | 9.50 |
| `default` | `ngspice` | 4.441 | 1.000 | 58.93 | 85.80 | 79.81 | 9.50 |
| `default` | `spectre` | 4.374 | 1.000 | 59.09 | 85.48 | 78.77 | 9.52 |

## Per-engine deltas vs python

| Condition | Engine | Metric | Python | Actual | Rel Δ % | OK |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `default` | `ngspice` | `max_inl_lsb` | 4.44091 | 4.44091 | 0.00 | yes |
| `default` | `ngspice` | `max_dnl_lsb` | 1 | 1 | 0.00 | yes |
| `default` | `ngspice` | `sndr_db` | 58.9216 | 58.9259 | 0.01 | yes |
| `default` | `ngspice` | `sfdr_db` | 85.66 | 85.7984 | 0.16 | yes |
| `default` | `ngspice` | `thd_db` | 79.8524 | 79.8136 | 0.05 | yes |
| `default` | `ngspice` | `enob_bits` | 9.49528 | 9.49599 | 0.01 | yes |
| `default` | `spectre` | `max_inl_lsb` | 4.44091 | 4.37449 | 1.50 | yes |
| `default` | `spectre` | `max_dnl_lsb` | 1 | 1 | 0.00 | yes |
| `default` | `spectre` | `sndr_db` | 58.9216 | 59.0949 | 0.29 | yes |
| `default` | `spectre` | `sfdr_db` | 85.66 | 85.4759 | 0.21 | yes |
| `default` | `spectre` | `thd_db` | 79.8524 | 78.7688 | 1.36 | yes |
| `default` | `spectre` | `enob_bits` | 9.49528 | 9.52408 | 0.30 | yes |

## Metric spread

| Condition | Metric | Spread % | Tol % | OK |
| --- | --- | ---: | ---: | --- |
| `default` | `max_inl_lsb` | 1.50 | 2.0 | yes |
| `default` | `max_dnl_lsb` | 0.00 | 2.0 | yes |
| `default` | `sndr_db` | 0.29 | 2.0 | yes |
| `default` | `sfdr_db` | 0.21 | 2.0 | yes |
| `default` | `thd_db` | 1.36 | 2.0 | yes |
| `default` | `enob_bits` | 0.30 | 2.0 | yes |

Spread % is the worst relative delta vs Python among ngspice and Spectre.
LSB metrics with a near-zero reference use a 0.02 LSB absolute band.

All metrics within 2.0% tolerance vs python: yes
