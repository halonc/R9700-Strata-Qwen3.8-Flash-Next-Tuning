#!/bin/sh
# Build the image encoder (strata-vision) with the HIP path from
# patches/001-vision-hip-gfx1201.patch, inside the same ROCm 10.1 container used for
# the engine. Reuses the llama.cpp checkout the engine build already fetched.
set -eu

IMAGE=${IMAGE:-rocm/dev-ubuntu-24.04:10.1.0-full}
SRC=${SRC:-$PWD/src}
BUILD_DIR=${BUILD_DIR:-$PWD/build-vision}
NAME=${NAME:-strata-build}          # the container build-engine.sh created
ARCH=${ARCH:-gfx1201}

git -C "$SRC" checkout v0.1.43
patch -p1 -d "$SRC" --dry-run < "$(dirname "$0")/../patches/001-vision-hip-gfx1201.patch" >/dev/null 2>&1 \
  && patch -p1 -d "$SRC" < "$(dirname "$0")/../patches/001-vision-hip-gfx1201.patch" \
  || echo "patch already applied (or does not apply cleanly) -- check tools/vision/CMakeLists.txt"

docker exec "$NAME" cmake -S /src/tools/vision -B /build-vision -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DLLAMA_DIR=/src/third_party/llama.cpp \
  -DSTRATA_PORTABLE=OFF

docker exec "$NAME" cmake --build /build-vision --target strata-vision -j "$(nproc)"

# Confirm the encoder really built a HIP backend, not a silent CPU fallback.
docker exec "$NAME" sh -c 'grep -m1 "GGML_HIP:BOOL" /build-vision/CMakeCache.txt'
echo "encoder binary is at $BUILD_DIR/strata-vision"
