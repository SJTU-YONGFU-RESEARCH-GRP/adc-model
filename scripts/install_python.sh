#!/usr/bin/env bash
# Create a virtual environment and install adc-model from pyproject.toml.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-${ROOT_DIR}/.venv}"
MIN_PYTHON_VERSION="3.10"
INSTALL_DEV=1

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Create a Python virtual environment and install this project in editable mode.

Options:
  --dev       Install dev dependencies (pytest, ruff, etc.). Default.
  --no-dev    Install runtime dependencies only (matplotlib, numpy).
  --recreate  Remove an existing virtual environment before installing.
  -h, --help  Show this help message.

Environment:
  VENV_DIR    Virtual environment path (default: ${ROOT_DIR}/.venv)

After installation, activate the environment:
  source ${VENV_DIR}/bin/activate
EOF
}

version_ge() {
    # Return success when $1 >= $2 (semver-like major.minor).
    local left="${1#python}"
    local right="${2#python}"
    IFS='.' read -r left_major left_minor _ <<<"${left}"
    IFS='.' read -r right_major right_minor _ <<<"${right}"
    if (( left_major > right_major )); then
        return 0
    fi
    if (( left_major < right_major )); then
        return 1
    fi
    (( left_minor >= right_minor ))
}

find_python() {
    local candidate version
    for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
        if ! command -v "${candidate}" >/dev/null 2>&1; then
            continue
        fi
        version="$("${candidate}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
        if version_ge "${version}" "${MIN_PYTHON_VERSION}"; then
            echo "${candidate}"
            return 0
        fi
    done
    return 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dev)
            INSTALL_DEV=1
            ;;
        --no-dev)
            INSTALL_DEV=0
            ;;
        --recreate)
            RECREATE=1
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
    shift
done

PYTHON="$(find_python)" || {
    echo "Error: Python ${MIN_PYTHON_VERSION}+ is required but was not found on PATH." >&2
    exit 1
}

echo "Using ${PYTHON} ($(${PYTHON} --version))"

venv_needs_recreate() {
    [[ ! -d "${VENV_DIR}" ]] && return 0
    local cfg="${VENV_DIR}/pyvenv.cfg"
    [[ ! -f "${cfg}" ]] && return 0
    # venv moved/renamed: activate scripts keep the old absolute path
    if grep -q 'command = .* -m venv ' "${cfg}"; then
        local recorded
        recorded="$(sed -n 's/^command = .* -m venv //p' "${cfg}" | head -1)"
        if [[ -n "${recorded}" && "${recorded}" != "${VENV_DIR}" ]]; then
            echo "Virtual environment was created at ${recorded} (project path changed)."
            return 0
        fi
    fi
    # Python version mismatch (e.g. venv built with 3.9, now requiring 3.10+)
    if [[ -x "${VENV_DIR}/bin/python" ]]; then
        local venv_version
        venv_version="$("${VENV_DIR}/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
        if ! version_ge "${venv_version}" "${MIN_PYTHON_VERSION}"; then
            echo "Virtual environment uses Python ${venv_version} (< ${MIN_PYTHON_VERSION})."
            return 0
        fi
    fi
    return 1
}

if [[ "${RECREATE:-0}" -eq 1 ]] || venv_needs_recreate; then
    if [[ -d "${VENV_DIR}" ]]; then
        echo "Removing existing virtual environment at ${VENV_DIR}"
        rm -rf "${VENV_DIR}"
    fi
fi

if [[ ! -d "${VENV_DIR}" ]]; then
    echo "Creating virtual environment at ${VENV_DIR}"
    "${PYTHON}" -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip

if [[ "${INSTALL_DEV}" -eq 1 ]]; then
    echo "Installing adc-model with dev dependencies..."
    python -m pip install -e "${ROOT_DIR}[dev]"
else
    echo "Installing adc-model (runtime dependencies only)..."
    python -m pip install -e "${ROOT_DIR}"
fi

echo
echo "Installation complete."
echo "Activate the environment with:"
echo "  source ${VENV_DIR}/bin/activate"
