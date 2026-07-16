#!/usr/bin/env bash
# Build and push Aryx images to Docker Hub (user: giggsodocker).
#
# Usage:
#   docker login   # once — must be giggsodocker (or a collaborator)
#   ./scripts/docker-hub-publish.sh              # tags: latest + git short SHA
#   ./scripts/docker-hub-publish.sh v1.0.0       # also tag as v1.0.0
#
# Images:
#   giggsodocker/aryx-lite       — Python API / worker / MCP (root Dockerfile)
#   giggsodocker/aryx-lite-web   — Next.js UI (apps/web/Dockerfile)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REGISTRY_USER="${DOCKERHUB_USER:-giggsodocker}"
API_IMAGE="${REGISTRY_USER}/aryx-lite"
WEB_IMAGE="${REGISTRY_USER}/aryx-lite-web"
# Version from arg, else pyproject.toml project.version (e.g. 1.0.0).
if [[ -n "${1:-}" ]]; then
  VERSION_TAG="$1"
else
  VERSION_TAG="$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])" 2>/dev/null || true)"
fi
GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo local)"
TAGS=("latest" "$GIT_SHA")
if [[ -n "$VERSION_TAG" ]]; then
  TAGS+=("$VERSION_TAG")
  # Also push v-prefixed semver if bare X.Y.Z was given
  if [[ "$VERSION_TAG" =~ ^[0-9]+\.[0-9]+ ]]; then
    TAGS+=("v${VERSION_TAG}")
  fi
fi

# Prefer BuildKit; fall back to classic builder if buildx perms fail (common on Desktop).
build_img() {
  local tag="$1" dockerfile="$2" context="$3"
  if ! docker build -t "$tag" -f "$dockerfile" "$context"; then
    echo "BuildKit failed — retrying with DOCKER_BUILDKIT=0"
    DOCKER_BUILDKIT=0 docker build -t "$tag" -f "$dockerfile" "$context"
  fi
}

echo "==> Building ${API_IMAGE} (api/worker/mcp)"
build_img "${API_IMAGE}:latest" Dockerfile .

echo "==> Building ${WEB_IMAGE} (web)"
build_img "${WEB_IMAGE}:latest" apps/web/Dockerfile apps/web

for tag in "${TAGS[@]}"; do
  [[ "$tag" == "latest" ]] && continue
  docker tag "${API_IMAGE}:latest" "${API_IMAGE}:${tag}"
  docker tag "${WEB_IMAGE}:latest" "${WEB_IMAGE}:${tag}"
done

echo "==> Checking Docker Hub login (must be ${REGISTRY_USER} or a collaborator)"
if ! docker push --help >/dev/null 2>&1; then
  echo "docker not available"
  exit 1
fi
# Probe auth with a dry failure message path: attempt push; if denied, tell user to login.
echo "If push is denied, run:  docker login   (username: ${REGISTRY_USER})"
echo "Prefer an Access Token from https://hub.docker.com/settings/security"

echo "==> Pushing tags: ${TAGS[*]}"
for tag in "${TAGS[@]}"; do
  docker push "${API_IMAGE}:${tag}"
  docker push "${WEB_IMAGE}:${tag}"
done

echo
echo "Published:"
for tag in "${TAGS[@]}"; do
  echo "  docker pull ${API_IMAGE}:${tag}"
  echo "  docker pull ${WEB_IMAGE}:${tag}"
done
echo
echo "Hub:"
echo "  https://hub.docker.com/r/${API_IMAGE}"
echo "  https://hub.docker.com/r/${WEB_IMAGE}"
echo
echo "Run with compose (pulls prebuilt if present):"
echo "  docker compose pull api web worker mcp"
echo "  docker compose up -d"
