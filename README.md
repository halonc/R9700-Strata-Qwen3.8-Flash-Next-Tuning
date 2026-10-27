# Strata 176B MoE on a single AMD R9700 (RDNA4 / gfx1201)

English | [中文](README.zh.md)

A full day of measurements, the container recipe, the two patches and the tuning knobs that
actually moved the needle — running **Qwen3.8-Flash-Next 176B MoE in IQ3_XXS** on **one
32 GB Radeon AI PRO R9700**, served by **Strata v0.1.43** in a **ROCm 10.1 container**.

This is not a "look how fast we are" repo. It is a reproducible setup, the arithmetic that
explains where the ceiling is, and an honest list of the knobs we spent time on that did
**not** help. Before you burn an evening on a flag, read
[Already tested, did not help](docs/DEAD-ENDS.md).

Every number below is a measurement from this machine. Every table is generated from the raw
JSON in [`bench/data/`](bench/data).

---

## The day at a glance

![Three builds of Strata on one R9700: prefill 1,747 then 2,232 then 1,940 tok/s; decode 58.8 then 73.2 then 93.2 tok/s, peak 108](assets/performance-comparison.png)

Three builds of the **same engine on the same card**. All three already ran `--adapt-every 1` and
`STRATA_HIP_WMMA=1`, so only two things differ between them: the hipBLASLt tuning table, and the
ROCm version. The tuning table is the prefill win; the ROCm 10.1 container is the decode win.
For reference, the morning starting point on a different engine — same card, same window — was
1,300 prefill and 57–63 decode.

---

## The numbers

Final state (ROCm 10.1 container, `--spec 4`, `--adapt-every 1`, `sampling.temperature 0.3`,
262,144-token window, 1K output, cache-pollution guards on — see
[docs/METHODOLOGY.md](docs/METHODOLOGY.md)):

| Metric | Measured |
|---|---|
| Decode | **95–99 tok/s steady** (acceptance 86–92%), peak **108** |
| Prefill | **1,900–2,100 tok/s** at 16–64K context, **1,800** at 128K, **1,534** at 230K |
| Context window | **262,144** configured; a ~256K prompt is **rejected (HTTP 400)**, so the usable ceiling is ~240–245K |
| Image request | **3.8 s** with the HIP image encoder (14–16 s with the CPU encoder) |
| Cross-conversation cache | **12 slots / 12 GiB** RAM (raised 2026-10-27 from 8 slots / 6 GiB): cold 4.1 s → **hot 0.54 s**, 8/8 hits measured at the 8-slot setting |
| Session save / restore | 237 MB in **2.6 s** / back in **0.4 s**, survives a container restart. The snapshot is now **2.28 GB** (see [FINDINGS §6](docs/FINDINGS.md)) |
| Cold start to first token available | **85 s** |

Against the starting point of the same day (a different engine, same card, same window):
prefill 1,300 → **1,900–2,230**, decode 57–63 → **95–99**.

---

## The two things that decide speed on this machine

**1. The PCIe link, not the GPU.** The host platform is PCIe 3.0 (Cascade Lake) and the card's
upstream port reports `8GT/s (downgraded)`, so the R9700 runs at **Gen3 x16**. Measured
host↔GPU bandwidth: **13.8 GB/s**, identical at 1, 2 and 4 concurrent streams — it is a hard
link ceiling, not a scheduling problem. Any design that streams model state across PCIe every
decode step is capped by that number. See [docs/HARDWARE.md](docs/HARDWARE.md).

**2. The speculative-decoding acceptance rate, not the context length.** With `--spec 4`, each
step yields `1 + 4 × acceptance` tokens. On this machine the acceptance rate swings between
**55% and 93% depending on what the model is writing** — structured text and code sit high,
free-form prose sits low. That single variable explains a 3× spread in decode speed, and no
flag we tried stabilised it. See [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

Both facts are visible in the raw data: in the same clean matrix, decode ranged
**30.6 → 93.4 tok/s** while the context ladder was monotonic.

---

## What actually helped

| Change | Measured effect | Evidence |
|---|---|---|
| `--adapt-every 1` (adaptive expert tier) | greedy decode **42.3 → 119.5**, 4-way aggregate **42.9 → 72.3**, expert hit rate 64–79% → **100%** | `strata-batch4-cache4g.json` vs `strata-adapt1-r2.json` |
| `STRATA_HIP_WMMA=1` (+ `STRATA_PREFILL_RING=96`) | 15K prefill **1,709 → 2,336** (+37%) | `strata-wmma-off.json` vs `strata-wmma-on-steady.json` |
| hipBLASLt tuning table on **ROCm 7.2.4** (hipBLASLt 1.2.2) | matrix prefill mean **1,747 → 2,232** (+28%), per bucket **+22% to +48%** | `matrix-clean-T1-baseline.json` vs `matrix-clean-T3-table.json` |
| **ROCm 10.1 container** (self-built engine) | decode mean **73 → 92–93**, peak **108**; costs ~13% prefill (2,232 → 1,940) | `matrix-clean-T3-table.json` vs `matrix-clean-RCm10*.json` |
| HIP image encoder ([patch](patches/001-vision-hip-gfx1201.patch)) | image request **14–16 s → 3.8 s** | `docs/TIMELINE.md` §7 |
| `sampling: {temperature 0.3, top_p 0.95, top_k 20}` | acceptance **72% → 83%**, decode 50.2 → 52.4 on the same three prompts | `ab-spec-notemp-greedy.json` vs `ab-spec-notemp-t03.json` |

The last row is a trade, not a win: it buys determinism for engineering work, not speed.

---

## Final configuration

`config/strata-final.json` is the live config, paths parameterised. The engine flags:

```
--prefill 8192            --spec 4 --spec-min-p 0.5
--max-context 262144      --kv int8 --kv-resident 32768
--adapt-every 1           --expert-cache auto
--pool-workers 15         --vram-reserve-mib 1024   --pcie-frac 0
--conversation-cache-mib 12288 --conversation-cache-slots 12
--conversation-cache-min-tokens 4096 --conversation-cache-min-free-mib 3072
--prompt-cache-every 4096 --prompt-cache-tail
--vision
```

plus `STRATA_HIP_WMMA=1`, `STRATA_PREFILL_RING=96`, and a `sampling` block
(`temperature 0.3, top_p 0.95, top_k 20`). No `--batch`: it is mutually exclusive with
session save/restore and costs 30% of single-stream decode.

---

## Directory layout

```
docs/            TIMELINE (the whole day, in order), HARDWARE, ENGINE-COMPARISON,
                 FINDINGS (every matrix), DEAD-ENDS, METHODOLOGY
reproduce/       Dockerfile, docker-compose.yml, entrypoint.sh, autosave.sh,
                 build-engine.sh, build-vision-hip.sh, launch.env, README.md (runbook)
patches/         PATCHSET.md + 001-vision-hip-gfx1201.patch
config/          strata-final.json  (the measured-best config)
tuning/          gfx1201-hipblaslt-100401.txt, cases.txt, README.md
bench/           the scripts that produced every number, and bench/data/ with the raw JSON
```

---

## Quick start

```bash
# 0. Requirements: gfx1201 card, host amdgpu/KFD (6.19.x is what we verified), Docker.
#    Model files are NOT in this repo — see NOTICE.md. Put them in $STRATA_MODEL_DIR.

# 1. Build the engine inside a ROCm 10.1 container (the arch flag is the trap:
#    CMAKE_HIP_ARCHITECTURES=gfx1201, NOT GPU_TARGETS).
./reproduce/build-engine.sh

# 2. Build the image encoder with the HIP patch applied.
patch -p1 -d src < patches/001-vision-hip-gfx1201.patch
./reproduce/build-vision-hip.sh

# 3. Build the runtime image and start it.
cp config/strata-final.json ./config/strata-final.json   # edit the /models paths first
docker build -f reproduce/Dockerfile -t strata-hip10:prod .
docker compose -f reproduce/docker-compose.yml up -d

# 4. Verify the engine actually loaded what you think it loaded.
curl -s localhost:8080/v1/models | head -c 400
docker logs strata-r9700 2>&1 | grep -E "session is up|adaptive tier|tuning enabled"

# 5. Re-run the matrix that produced every number in this README.
cd bench && python3 matrix_port.py
```

Full step-by-step, including the five build traps, is in
[reproduce/README.md](reproduce/README.md).

---

## Caveats we are not hiding

- **Decode is not stable at 100.** It is 95–99 at ≤32K context with high acceptance and drifts
  to ~87 at 128K, ~57 at 230K. The drift is attention cost plus KV streaming from 64K up —
  **not** MTP degradation; acceptance at 64K and 128K measured 80–87%, the same as short context.
- **`--adapt-every 1` makes sampled output non-reproducible** (the expert tier changes between
  requests). For byte-identical reruns you would have to freeze the tier and lose the speed.
- **`--batch` and session save/restore are mutually exclusive** in v0.1.43 (`/slots/0` returns
  501 with batch on). We chose no-batch.
- **Automatic session restore is safe but not prefix-checked.** We tested it: after a restore,
  an unrelated conversation re-reads from scratch (`cache_n=0`) and answers correctly. It never
  silently continues someone else's KV. It also will not pick a conversation for you.
- **A hipBLASLt tuning table is version-scoped.** Ours (`100401`) produced **0%** on ROCm 10.1,
  matching upstream's own note that hipBLASLt 1.4.1 is already close on the R9700. The +28%
  came from the 1.2.2 table on ROCm 7.2.4.
- **Upgrading the host GPU driver buys nothing here.** With the card passed through, the host
  binds `vfio-pci` and loads no `amdgpu` at all; the driver that matters lives in the guest.

---

## Upstream

- Strata: MIT, Copyright (c) 2026 Niko1221 and the Strata contributors. Tag used: `v0.1.43`.
- llama.cpp: used by Strata's build and by `tools/vision` for `mtmd`.
- ROCm base image: `rocm/dev-ubuntu-24.04:10.1.0-full`.

See [NOTICE.md](NOTICE.md) for what is ours and what is not included.

## License

MIT — see [LICENSE](LICENSE).
