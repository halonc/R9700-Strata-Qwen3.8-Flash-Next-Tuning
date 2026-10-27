# Runbook: build and run this on a gfx1201 card

Verified on: one R9700 (32 GB, gfx1201) passed through to a Linux guest, host driver
`amdgpu 6.19.14`, ROCm **10.1.0** user space in a container, Strata **v0.1.43**.

## 0. Prerequisites

- A gfx1201 card visible to the machine that will run the container (`/dev/kfd`, `/dev/dri`).
- Docker with device passthrough working (`group_add` for the render/video groups).
- Model files, which are **not** in this repository (see [NOTICE.md](../NOTICE.md)): the IQ3_XXS
  GGUF shards, the PLE shard, the MTP head, the quantisation pack, the expert profile and the
  `mmproj` file. Put them under `STRATA_MODEL_DIR`.
- ~40 GB of RAM free for the engine plus 6 GB for the conversation cache.

## 1. Build the engine

```bash
export STRATA_UPSTREAM=<upstream repository URL>
./reproduce/build-engine.sh
```

**Trap 1 — the architecture variable.** It is `CMAKE_HIP_ARCHITECTURES=gfx1201`. Using
`GPU_TARGETS` instead builds gfx1100 silently and the binary fails to load on the card. The script
greps `CMakeCache.txt` at the end precisely so you catch this there rather than at runtime.

**Trap 2 — `docker run --rm` discards your toolchain.** The build container here is persistent and
every step is a `docker exec`. With `--rm` you reinstall cmake/ninja on every invocation and the
second build fails with something that looks like a missing dependency.

**Trap 3 — the engine binary is not the server.** The HTTP API comes from upstream `serve/`. The
image needs `serve/`, `tools/`, the engine binary, the encoder binary and the Python deps
(`python3-aiohttp`, `python3-jinja2`, `python3-yaml`, `python3-regex`, `python3-numpy`).

## 2. Build the image encoder with the HIP patch

```bash
./reproduce/build-vision-hip.sh
```

Why: upstream `tools/vision` only offers CPU and CUDA flavours, so AMD is CPU-only without this.
Measured effect: **14–16 s → 3.8 s** per image request. Details in
[patches/PATCHSET.md](../patches/PATCHSET.md).

## 3. Assemble the image and start it

```bash
./reproduce/prepare-context.sh
docker build -f reproduce/Dockerfile -t strata-hip10:prod ./image-context

cp reproduce/launch.env .env          # edit the three paths
cp config/strata-final.json ./config/strata-final.json
docker compose -f reproduce/docker-compose.yml up -d
```

**Trap 4 — runtime library path.** Without `LD_LIBRARY_PATH=/opt/rocm/lib` the engine cannot find
`libhip_hcc`/ROCm libraries and dies at startup. It is set in both the Dockerfile and the compose
file.

**Trap 5 — compose `VAR=` is not `VAR`.** An empty-string ROCm device variable
(`ROCR_VISIBLE_DEVICES=`) is read as "zero GPUs available" and the container dies immediately.
The compose file in this repo deliberately has no ROCm device variables at all; if you add any,
write them without `=`.

**Trap 6 — user mapping.** `user: "1000:1000"` matters: run as root and the session files in
`/sessions` end up owned by root, then the next start cannot read them.

**Trap 7 — image input needs Pillow.** Without it the server answers
`this image format needs Pillow (python -m pip install pillow)` for WebP input and for JPEGs with
an EXIF orientation other than 1. `python3-pil` is in the Dockerfile. If you add it to a running
container (`python3 -m pip install --break-system-packages pillow`) it takes effect immediately:
the import is inside the request handler, not at startup.

## 4. Verify that what you configured is what is running

Do not trust the config file; read the log.

```bash
curl -s localhost:8080/v1/models | head -c 400
docker logs strata-r9700 2>&1 | grep -E "session is up|adaptive tier|tuning enabled|ROCk module"
```

Expected lines:

```
session is up: n_ctx=262144 n_gpu_layers=-1 input_modalities=[text, image]
adaptive tier: 437 experts swapped in
routed entries per window: VRAM 98.6% / CPU 1.4%
ROCk module version 6.19.14 is loaded
```

The last one is the compatibility answer: ROCm 10.1 **user space** running against a host kernel
driver of 6.19.14. Container isolation covers user space only — the KFD ABI check is what would
have failed, and it passed.

`GET /metrics` reports `engine.spec = 6` and `engine.mtp_max = 4`. `mtp_max` is the actual MTP
depth; `spec` counts verify-window rows. Do not read `spec` as the depth.

## 5. Optional: hipBLASLt tuning table

```bash
STRATA_HIPBLASLT_TUNING=/path/to/gfx1201-hipblaslt-100401.txt
```

Then confirm `prefill gemm: hipBLASLt tuning enabled (43 rows, gfx1201, version 100401)` in the
log. On ROCm 10.1 this gains **0%** (measured, see [tuning/README.md](../tuning/README.md)); on
ROCm 7.2.4 with hipBLASLt 1.2.2 the upstream table gains **+22% to +48% prefill**. Tables are
scoped to a hipBLASLt version and an architecture — a mismatch is silently ignored.

## 6. Autosave and automatic restore

`entrypoint.sh` starts `autosave.sh`, waits for `/v1/models` to answer (up to 6 minutes), then
restores the newest `autosave-*.bin` into slot 0.

Measured end to end: 1,863-token conversation → save → `docker restart` (96 s to ready) → continue
it → `cache_n=1863`, 18 tokens re-read, **TTFT 0.54 s**.

Safety, measured: after a restore, an **unrelated** conversation re-reads from scratch
(`cache_n=0`) and answers correctly. The engine does not silently continue someone else's KV, but
it also will not choose a conversation for you.

Session save/restore requires batch to be **off**: with `--batch`, `/slots/0` returns 501.

**Size warning.** With a large conversation cache the snapshot is not small: at 12 slots / 12 GiB
parked, one autosave file measured **2.28 GB**. `AUTOSAVE_KEEP` should be set accordingly — we run
2, not 4.

## 7. Rollback

The image is a tag, so rollback is a tag swap:

```bash
docker compose -f reproduce/docker-compose.yml down
sed -i 's/strata-hip10:prod/strata-hip10:previous/' reproduce/docker-compose.yml
docker compose -f reproduce/docker-compose.yml up -d
```

Config rollback: keep a copy of the previous `strata-final.json` next to it. The engine reads the
file at startup, so a config change is a restart, and a restart costs 85 s.

## 8. Startup cost, so you know what to expect

| Stage | Time |
|---|---|
| Container start → API answering | **85 s** (warm page cache) / 215 s (cold) |
| First 1–2 requests after start | **not measurable** — adaptive tier still warming (45–50 tok/s) |
| Steady state | 95–99 tok/s |

Warm up with a throwaway request before benchmarking. See [docs/METHODOLOGY.md](../docs/METHODOLOGY.md).
