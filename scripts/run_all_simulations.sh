#!/usr/bin/env bash
# Run all six ADC simulations: static + dynamic for python, ngspice, and spectre.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_ROOT="${OUTPUT_ROOT:-${ROOT_DIR}/outputs}"
EXTRA_ARGS=()

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS] [-- EXTRA_ARGS...]

Run six simulations (static INL/DNL and dynamic FFT for each engine):
  - Python behavioral model
  - ngspice behavioral netlists
  - Cadence Spectre testbenches

Results are written under:
  \${OUTPUT_ROOT}/python/
  \${OUTPUT_ROOT}/ngspice/
  \${OUTPUT_ROOT}/spectre/

Each directory contains static_waveform.csv, inl_dnl.svg, dynamic_waveform.csv,
spectrum.svg, SUMMARY.md, logs/, and veriloga/ artifacts.

Options:
  --ideal          Pass --ideal to each run (quantizer-limited, no noise).
  --output-root DIR
                   Base output directory (default: ${ROOT_DIR}/outputs).
  --skip-missing   Skip ngspice/spectre when the binary is not on PATH.
  -h, --help       Show this message.

Environment:
  OUTPUT_ROOT      Same as --output-root.
  VENV_DIR         If set, use \${VENV_DIR}/bin/python when present.

Examples:
  $(basename "$0")
  $(basename "$0") --ideal --output-root outputs/benchmark
  $(basename "$0") -- --bits 12 --fs 2e6

Requires: Python 3.10+ with adc-model installed (see scripts/install_python.sh).
Optional: ngspice and spectre on PATH for external simulators.
EOF
}

SKIP_MISSING=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h | --help)
            usage
            exit 0
            ;;
        --ideal)
            EXTRA_ARGS+=(--ideal)
            shift
            ;;
        --output-root)
            OUTPUT_ROOT="$2"
            shift 2
            ;;
        --skip-missing)
            SKIP_MISSING=1
            shift
            ;;
        --)
            shift
            EXTRA_ARGS+=("$@")
            break
            ;;
        *)
            EXTRA_ARGS+=("$1")
            shift
            ;;
    esac
done

cd "${ROOT_DIR}"

VENV_DIR="${VENV_DIR:-${ROOT_DIR}/.venv}"
if [[ -x "${VENV_DIR}/bin/python" ]]; then
    PYTHON="${VENV_DIR}/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
else
    echo "error: python3 not found (run scripts/install_python.sh)" >&2
    exit 1
fi

if ! "${PYTHON}" -c "import adc_model" 2>/dev/null; then
    export PYTHONPATH="${ROOT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"
    if ! "${PYTHON}" -c "import adc_model" 2>/dev/null; then
        echo "error: adc_model not importable; run scripts/install_python.sh" >&2
        exit 1
    fi
fi

require_command() {
    local name="$1"
    local label="$2"
    if command -v "${name}" >/dev/null 2>&1; then
        return 0
    fi
    if [[ "${SKIP_MISSING}" -eq 1 ]]; then
        echo "warning: ${label} (${name}) not found; skipping" >&2
        return 1
    fi
    echo "error: ${label} (${name}) not found on PATH (use --skip-missing to omit)" >&2
    exit 1
}

run_engine() {
    local engine="$1"
    local out_dir="${OUTPUT_ROOT}/${engine}"
    mkdir -p "${out_dir}"

    echo ""
    echo "========== ${engine}: static INL/DNL =========="
    "${PYTHON}" scripts/run_static.py \
        --simulator "${engine}" \
        --output-dir "${out_dir}" \
        "${EXTRA_ARGS[@]}"

    echo ""
    echo "========== ${engine}: dynamic spectrum =========="
    "${PYTHON}" scripts/run_dynamic.py \
        --simulator "${engine}" \
        --output-dir "${out_dir}" \
        "${EXTRA_ARGS[@]}"
}

echo "Output root: ${OUTPUT_ROOT}"
echo "Extra args : ${EXTRA_ARGS[*]-<none>}"

ENGINES_RUN=(python)

run_engine python

if require_command ngspice "ngspice"; then
    ENGINES_RUN+=(ngspice)
    run_engine ngspice
fi

if require_command spectre "Cadence Spectre"; then
    ENGINES_RUN+=(spectre)
    run_engine spectre
fi

echo ""
echo "All requested simulations finished."
echo "Summaries:"
for engine in "${ENGINES_RUN[@]}"; do
    summary_path="${OUTPUT_ROOT}/${engine}/SUMMARY.md"
    if [[ -f "${summary_path}" ]]; then
        echo "  ${engine} -> ${summary_path}"
    else
        echo "  ${engine} -> ${summary_path} (missing)" >&2
    fi
done

echo ""
echo "========== summary and comparisons =========="
COMPARE_ARGS=(--output-root "${OUTPUT_ROOT}" --check-parity --engines "${ENGINES_RUN[@]}")
if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
    COMPARE_ARGS+=("${EXTRA_ARGS[@]}")
fi
"${PYTHON}" scripts/compare_engines.py "${COMPARE_ARGS[@]}"
