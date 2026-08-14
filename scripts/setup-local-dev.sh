#!/usr/bin/env bash
# Copyright (c) Microsoft Corporation.
# SPDX-License-Identifier: MIT
#
# Prepare the local Tiger PoC development environment.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

usage() {
  cat <<'EOF'
Usage: setup-local-dev.sh [options]

Prepare local directories and host prerequisites for Tiger PoC development.

Options:
  --check-only     Check host tools without creating files or directories.
  --fetch-models   Fetch the configured model bundle after setup.
  --verify-models  Verify the model bundle after setup.
  --help           Show this help text.
EOF
}

pass() {
  printf '%bPASS%b: %s\n' "$GREEN" "$NC" "$1"
}

warn() {
  printf '%bWARN%b: %s\n' "$YELLOW" "$NC" "$1"
}

fail() {
  printf '%bFAIL%b: %s\n' "$RED" "$NC" "$1" >&2
}

check_command() {
  local command_name="$1"
  local description="$2"
  if command -v "$command_name" >/dev/null 2>&1; then
    pass "$description"
    return 0
  fi
  fail "$description is not installed or is not on PATH"
  return 1
}

check_prerequisites() {
  local failures=0

  check_command git "Git" || ((failures += 1))
  check_command python3 "Python 3" || ((failures += 1))
  check_command curl "curl" || ((failures += 1))
  check_command sha256sum "sha256sum" || ((failures += 1))

  if command -v docker >/dev/null 2>&1; then
    if docker compose version >/dev/null 2>&1; then
      pass "Docker Compose"
    else
      fail "Docker Compose is not available"
      ((failures += 1))
    fi
  else
    warn "Docker is not installed; container commands will not be available"
  fi

  if ((failures > 0)); then
    return 1
  fi
}

prepare_directories() {
  mkdir -p \
    "$REPO_DIR/models/yolo" \
    "$REPO_DIR/models/florence-2" \
    "$REPO_DIR/models/phi-4-multimodal" \
    "$REPO_DIR/data/detections/detections" \
    "$REPO_DIR/data/detections/clips"
  pass "Local model and detection directories"
}

prepare_environment_file() {
  local environment_file="$REPO_DIR/.env"
  local example_file="$REPO_DIR/.env.example"

  if [[ -f "$environment_file" ]]; then
    pass ".env already exists"
  elif [[ -f "$example_file" ]]; then
    cp "$example_file" "$environment_file"
    pass "Created .env from .env.example"
  else
    warn "No .env.example found; skipped .env creation"
  fi
}

prepare_python_environment() {
  local project_dir="$REPO_DIR/apps/vision-pipeline"

  if [[ ! -f "$project_dir/pyproject.toml" ]]; then
    warn "apps/vision-pipeline has no pyproject.toml; skipped Python environment"
    return
  fi

  if [[ ! -d "$project_dir/.venv" ]]; then
    python3 -m venv "$project_dir/.venv"
    pass "Created Python virtual environment"
  else
    pass "Python virtual environment already exists"
  fi

  "$project_dir/.venv/bin/python" -m pip install --upgrade pip
  "$project_dir/.venv/bin/python" -m pip install -e "$project_dir[test]"
  pass "Installed vision-pipeline dependencies"
}

main() {
  local check_only=false
  local fetch_models=false
  local verify_models=false

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --check-only) check_only=true; shift ;;
      --fetch-models) fetch_models=true; shift ;;
      --verify-models) verify_models=true; shift ;;
      --help|-h) usage; return 0 ;;
      *) usage >&2; return 2 ;;
    esac
  done

  printf '=== Tiger PoC Local Development Setup ===\n'
  check_prerequisites

  if [[ "$check_only" == true ]]; then
    return 0
  fi

  prepare_directories
  prepare_environment_file
  prepare_python_environment

  if [[ "$fetch_models" == true ]]; then
    "$SCRIPT_DIR/fetch-model-bundle.sh"
  fi
  if [[ "$verify_models" == true ]]; then
    "$SCRIPT_DIR/fetch-model-bundle.sh" --verify
  fi

  printf '\nSetup completed.\n'
}

main "$@"