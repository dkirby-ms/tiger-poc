#!/usr/bin/env bash

set -u

failures=0

pass() {
    printf 'PASS: %s\n' "$1"
}

warn() {
    printf 'WARN: %s\n' "$1"
}

fail() {
    printf 'FAIL: %s\n' "$1"
    failures=$((failures + 1))
}

if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia_output=$(nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>/dev/null || true)
    if [[ -n "$nvidia_output" ]]; then
        driver_version=$(printf '%s\n' "$nvidia_output" | awk -F', ' 'NR == 1 { print $2 }')
        if awk -v version="$driver_version" 'BEGIN { exit !(version >= 570) }'; then
            pass "NVIDIA GPU is visible with driver ${driver_version}: ${nvidia_output}"
        else
            fail "NVIDIA driver ${driver_version} is older than the required 570"
        fi
    else
        fail "nvidia-smi is installed but cannot query a GPU"
    fi
else
    fail "nvidia-smi is not installed or is not on PATH"
fi

if command -v nvcc >/dev/null 2>&1; then
    cuda_version=$(nvcc --version | awk -F'release ' '/release/ { split($2, values, ","); print values[1]; exit }')
    if [[ -n "$cuda_version" ]]; then
        if awk -v version="$cuda_version" 'BEGIN { exit !(version >= 12.8) }'; then
            pass "CUDA toolkit ${cuda_version} meets the required 12.8 baseline"
        else
            fail "CUDA toolkit ${cuda_version} is older than the required 12.8"
        fi
    else
        warn "nvcc is installed but its version could not be parsed"
    fi
else
    warn "nvcc is not installed; this is acceptable when CUDA is supplied by container images"
fi

if command -v docker >/dev/null 2>&1; then
    pass "Docker is available"
    if docker compose version >/dev/null 2>&1; then
        pass "Docker Compose is available"
    else
        fail "Docker Compose is not available"
    fi
else
    warn "Docker is not available in this WSL2 distro; enable Docker Desktop WSL integration"
fi

if [[ "$failures" -gt 0 ]]; then
    printf '\nEnvironment verification failed with %d error(s).\n' "$failures"
    exit 1
fi

printf '\nEnvironment verification completed.\n'