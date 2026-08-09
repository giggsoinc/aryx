#!/usr/bin/env bash
# Build and push Aryx images to Docker Hub (user: giggsodocker).
#
# Usage:
#   docker login   # once — must be giggsodocker (or a collaborator)
#   ./scripts/docker-hub-publish.sh              # tags: version from pyproject + v-prefix + git short SHA
#   ./scripts/docker-hub-publish.sh 1.2.0        # explicit version override
#
# Policy: every push carries an explicit semver tag. `latest` is never
# pushed — deployments pin a version (compose defaults do too).
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
if [[ -z "$VERSION_TAG" ]]; then
  echo "ERROR: no version — pass one (./scripts/docker-hub-publish.sh 1.2.0) or set project.version in pyproject.toml"
  exit 1
fi
TAGS=("$VERSION_TAG" "$GIT_SHA")
# Also push v-prefixed semver if bare X.Y.Z was given
if [[ "$VERSION_TAG" =~ ^[0-9]+\.[0-9]+ ]]; then
  TAGS+=("v${VERSION_TAG}")
fi

# Hub images and the deployment hosts are linux/amd64 — pin it so builds
# from Apple Silicon don't silently produce arm64 images.
PLATFORM="${ARYX_BUILD_PLATFORM:-linux/amd64}"

# Prefer BuildKit; fall back to classic builder if buildx perms fail (common on Desktop).
build_img() {
  local tag="$1" dockerfile="$2" context="$3"
  if ! docker build --platform "$PLATFORM" -t "$tag" -f "$dockerfile" "$context"; then
    echo "BuildKit failed — retrying with DOCKER_BUILDKIT=0"
    DOCKER_BUILDKIT=0 docker build --platform "$PLATFORM" -t "$tag" -f "$dockerfile" "$context"
  fi
}

echo "==> Building ${API_IMAGE} (api/worker/mcp) [$PLATFORM]"
build_img "${API_IMAGE}:${VERSION_TAG}" Dockerfile .

echo "==> Building ${WEB_IMAGE} (web) [$PLATFORM]"
build_img "${WEB_IMAGE}:${VERSION_TAG}" apps/web/Dockerfile apps/web

# Subpath variant for reverse-proxy deployments (served under /aryx).
SUBPATH="${ARYX_SUBPATH:-/aryx}"
echo "==> Building ${WEB_IMAGE}:${VERSION_TAG}-subpath (basePath ${SUBPATH}) [$PLATFORM]"
if ! docker build --platform "$PLATFORM" --build-arg "ARYX_BASE_PATH=${SUBPATH}" \
     -t "${WEB_IMAGE}:${VERSION_TAG}-subpath" -f apps/web/Dockerfile apps/web; then
  DOCKER_BUILDKIT=0 docker build --platform "$PLATFORM" --build-arg "ARYX_BASE_PATH=${SUBPATH}" \
     -t "${WEB_IMAGE}:${VERSION_TAG}-subpath" -f apps/web/Dockerfile apps/web
fi

for tag in "${TAGS[@]}"; do
  [[ "$tag" == "$VERSION_TAG" ]] && continue
  docker tag "${API_IMAGE}:${VERSION_TAG}" "${API_IMAGE}:${tag}"
  docker tag "${WEB_IMAGE}:${VERSION_TAG}" "${WEB_IMAGE}:${tag}"
done

echo "==> Checking Docker Hub login (must be ${REGISTRY_USER} or a collaborator)"
if ! docker push --help >/dev/null 2>&1; then
  echo "docker not available"
  exit 1
fi
# Probe auth with a dry failure message path: attempt push; if denied, tell user to login.
echo "If push is denied, run:  docker login   (username: ${REGISTRY_USER})"
echo "Prefer an Access Token from https://hub.docker.com/settings/security"

echo "==> Pushing tags: ${TAGS[*]} (+ web ${VERSION_TAG}-subpath)"
for tag in "${TAGS[@]}"; do
  docker push "${API_IMAGE}:${tag}"
  docker push "${WEB_IMAGE}:${tag}"
done
docker push "${WEB_IMAGE}:${VERSION_TAG}-subpath"

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
