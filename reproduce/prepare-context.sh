#!/bin/sh
# Assemble the Docker build context. The image needs four things that live in three
# different places: the engine binary, the vision binary, and the upstream serve/ +
# tools/ trees (the HTTP API is serve/server.py -- the engine binary alone is not a
# server). Nothing model-related is copied: weights stay outside the image and are
# mounted read-only at runtime.
set -eu

CTX=${CTX:-$PWD/image-context}
ENGINE_BIN=${ENGINE_BIN:-$PWD/build-engine/strata}
VISION_BIN=${VISION_BIN:-$PWD/build-vision/strata-vision}
SRC=${SRC:-$PWD/src}                 # upstream checkout at v0.1.43

[ -x "$ENGINE_BIN" ] || { echo "missing engine binary: $ENGINE_BIN (run build-engine.sh)"; exit 1; }
[ -x "$VISION_BIN" ] || { echo "missing vision binary: $VISION_BIN (run build-vision-hip.sh)"; exit 1; }
[ -d "$SRC/serve" ]  || { echo "missing $SRC/serve -- point SRC at the upstream checkout"; exit 1; }

mkdir -p "$CTX"
cp "$ENGINE_BIN"  "$CTX/strata"
cp "$VISION_BIN"  "$CTX/strata-vision"
cp -a "$SRC/serve" "$CTX/serve"
cp -a "$SRC/tools" "$CTX/tools"
cp reproduce/autosave.sh reproduce/entrypoint.sh "$CTX/"
chmod +x "$CTX/autosave.sh" "$CTX/entrypoint.sh"

echo "build context ready: $CTX"
echo "then:  docker build -f reproduce/Dockerfile -t strata-hip10:prod $CTX"
