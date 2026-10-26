# NOTICE

Copyright (c) 2026 the R9700-Strata-Tuning authors. The original material in this
repository is released under the MIT License (see `LICENSE`).

## Upstream code this repository depends on

- **Strata** — the inference engine this record is about. Upstream
  `Copyright (c) 2026 Niko1221 and the Strata contributors`, MIT License. The engine
  is **not vendored here**: `reproduce/build-engine.sh` builds tag `v0.1.43` from
  upstream, and `patches/` contains only the delta authored by us.
- **llama.cpp** — pulled in by Strata's own build (FetchContent, `strata_llamacpp`),
  and used directly by `tools/vision` for the `mtmd` image encoder. Its license and
  notices travel with that checkout, not with this repository.
- **ROCm** — `rocm/dev-ubuntu-24.04:10.1.0-full` is used as the container base image.

## What is ours

- `patches/001-vision-hip-gfx1201.patch` — a three-line addition to
  `tools/vision/CMakeLists.txt` that gives the vision encoder a HIP path.
- `tuning/gfx1201-hipblaslt-100401.txt` and `tuning/cases.txt` — a hipBLASLt tuning
  table calibrated on our own card at the engine's GEMM shapes, plus the case list
  used to calibrate it.
- `reproduce/` (Dockerfile, compose, entrypoint, autosave loop, build scripts),
  `config/strata-final.json`, `bench/` scripts, and all of `docs/`.

## Not included

- **Model weights.** The 176B MoE GGUF shards, the PLE shard, the MTP head, the expert
  profile, the quantisation packs and the `mmproj` file are third-party artifacts with
  their own licenses. Obtain them separately and point `STRATA_MODEL_DIR` at them.
- **Engine and encoder binaries.** `strata` (14 MB) and `strata-vision` (78 MB) are
  build outputs; build them with the scripts in `reproduce/`.
- **Conversation snapshots.** `*.bin` session files are runtime state that contains live
  chat KV. They are git-ignored and were never committed.
- **Local paths, hostnames and machine layout.** Every path in `config/`,
  `reproduce/docker-compose.yml` and `bench/` is either relative or parameterised
  (`STRATA_MODEL_DIR`, `STRATA_CONFIG_DIR`, `STRATA_SESSION_DIR`, `COMPOSE_DIR`).
  Host names, LAN addresses and the surrounding virtualisation layout have been removed;
  `docs/HARDWARE.md` keeps only the hardware facts that change the measurement.

## A note on the numbers

Every table in `docs/` is generated from the raw JSON under `bench/data/`. If a table and
a JSON file disagree, the JSON is right and the table is a typo.
