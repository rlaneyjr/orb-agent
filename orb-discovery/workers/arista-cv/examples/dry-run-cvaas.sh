#!/usr/bin/env bash
# Dry-run arista-cv against CVaaS (https://www.arista.io).
#
# Usage:
#   export CV_TOKEN=...   # CVaaS service-account token (never logged)
#   ./examples/dry-run-cvaas.sh
#
# Optional env:
#   OUT_DIR            Output directory (default: /tmp/arista-cv-dry-run)
#   ORB_AGENT          Path to a local orb-agent binary
#   ORB_AGENT_IMAGE    Docker image (default: netboxlabs/orb-agent:latest)
#   WAIT_SECONDS       Max seconds to wait for dry-run JSON (default: 120)
set -euo pipefail

if [[ -z "${CV_TOKEN:-}" ]]; then
  echo "error: CV_TOKEN is required (CVaaS service-account token)." >&2
  echo "  export CV_TOKEN=... && $0" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
# examples/ → arista-cv → workers → orb-discovery; three ups from package = repo root
REPO_ROOT="$(cd "${PACKAGE_DIR}/../../.." && pwd)"
CONFIG="${SCRIPT_DIR}/agent-cvaas-dry-run.yaml"
OUT_DIR="${OUT_DIR:-/tmp/arista-cv-dry-run}"
WAIT_SECONDS="${WAIT_SECONDS:-120}"
IMAGE="${ORB_AGENT_IMAGE:-netboxlabs/orb-agent:latest}"

mkdir -p "${OUT_DIR}"

resolve_agent_bin() {
  if [[ -n "${ORB_AGENT:-}" ]]; then
    printf '%s\n' "${ORB_AGENT}"
    return 0
  fi
  if [[ -x "${REPO_ROOT}/build/orb-agent" ]]; then
    printf '%s\n' "${REPO_ROOT}/build/orb-agent"
    return 0
  fi
  if command -v orb-agent >/dev/null 2>&1; then
    command -v orb-agent
    return 0
  fi
  return 1
}

wait_for_output() {
  local deadline=$((SECONDS + WAIT_SECONDS))
  echo "Waiting up to ${WAIT_SECONDS}s for dry-run JSON under ${OUT_DIR} ..."
  while (( SECONDS < deadline )); do
    # shellcheck disable=SC2010
    if ls -1 "${OUT_DIR}"/*.json >/dev/null 2>&1; then
      echo "Dry-run output ready:"
      ls -la "${OUT_DIR}"/*.json
      return 0
    fi
    sleep 1
  done
  echo "error: timed out waiting for dry-run JSON in ${OUT_DIR}" >&2
  return 1
}

stop_pid() {
  local pid="$1"
  if kill -0 "${pid}" 2>/dev/null; then
    kill "${pid}" 2>/dev/null || true
    wait "${pid}" 2>/dev/null || true
  fi
}

run_local() {
  local agent_bin="$1"
  if ! command -v orb-worker >/dev/null 2>&1; then
    echo "error: local agent requires orb-worker on PATH." >&2
    echo "  pip install -e ${REPO_ROOT}/orb-discovery/worker" >&2
    echo "  pip install -e ${PACKAGE_DIR}" >&2
    return 1
  fi

  echo "Running local agent: ${agent_bin}"
  echo "Config: ${CONFIG}"
  echo "Output: ${OUT_DIR}"
  # CV_TOKEN is in the environment for ${CV_TOKEN} secret resolution; never echo it.
  "${agent_bin}" run -c "${CONFIG}" &
  local agent_pid=$!
  trap 'stop_pid '"${agent_pid}" EXIT
  wait_for_output
  stop_pid "${agent_pid}"
  trap - EXIT
}

run_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "error: docker not found and no usable local orb-agent binary." >&2
    echo "  Build one with: make agent_bin" >&2
    echo "  Or install Docker and retry (image: ${IMAGE})." >&2
    return 1
  fi

  echo "Running via Docker image: ${IMAGE}"
  echo "Config: ${CONFIG}"
  echo "Output: ${OUT_DIR}"
  docker run --rm \
    -e CV_TOKEN \
    -v "${CONFIG}:/opt/orb/agent.yaml:ro" \
    -v "${OUT_DIR}:/tmp/arista-cv-dry-run" \
    "${IMAGE}" \
    run -c /opt/orb/agent.yaml &
  local docker_pid=$!
  trap 'stop_pid '"${docker_pid}" EXIT
  wait_for_output
  stop_pid "${docker_pid}"
  trap - EXIT
}

if agent_bin="$(resolve_agent_bin)"; then
  if command -v orb-worker >/dev/null 2>&1; then
    run_local "${agent_bin}"
  else
    echo "note: found ${agent_bin} but orb-worker is not on PATH; using Docker."
    run_docker
  fi
else
  run_docker
fi

echo
echo "Inspect entities under ${OUT_DIR}."
echo "Confirm device hostnames/serials look correct and the token never appears in files or logs."
