#!/bin/sh
# Build Strata v0.1.43 with HIP for gfx1201, inside a ROCm 10.1 container.
#
# Two things this script exists to get right:
#   1. the arch variable is CMAKE_HIP_ARCHITECTURES, NOT GPU_TARGETS (the wrong one
#      silently builds gfx1100 and the binary will not load on an R9700);
#   2. the build container is persistent -- `docker run --rm` throws away cmake/ninja
#      on every invocation, which looks like "cmake is missing" the second time.
set -eu

IMAGE=${IMAGE:-rocm/dev-ubuntu-24.04:10.1.0-full}
SRC=${SRC:-$PWD/src}
BUILD_DIR=${BUILD_DIR:-$PWD/build-engine}
NAME=${NAME:-strata-build}
ARCH=${ARCH:-gfx1201}

# Upstream URL is deliberately not hard-coded here: pin the tag, not a mirror.
if [ ! -d "$SRC" ]; then
  : "${STRATA_UPSTREAM:?set STRATA_UPSTREAM to the upstream repository URL}"
  git clone "$STRATA_UPSTREAM" "$SRC"
fi
git -C "$SRC" checkout v0.1.43

if ! docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  docker run -d --name "$NAME" -v "$SRC":/src -v "$BUILD_DIR":/build "$IMAGE" sleep infinity
  docker exec "$NAME" apt-get update
  docker exec "$NAME" apt-get install -y --no-install-recommends \
      cmake ninja-build git build-essential python3
fi

docker exec "$NAME" cmake -S /src -B /build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DSTRATA_ENABLE_HIP=ON \
  -DCMAKE_HIP_ARCHITECTURES="$ARCH" \
  -DSTRATA_BUILD_TESTS=OFF

docker exec "$NAME" cmake --build /build --target strata -j "$(nproc)"

# Confirm the target actually compiled for the card you have.
docker exec "$NAME" sh -c 'grep -m1 "CMAKE_HIP_ARCHITECTURES" /build/CMakeCache.txt'
echo "engine binary is at $BUILD_DIR/strata"
