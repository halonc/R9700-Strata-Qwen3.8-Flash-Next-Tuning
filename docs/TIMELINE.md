# The whole day, in order

One day, one card, from "the published numbers don't reproduce" to a container that serves 176B
MoE at 95–99 tok/s. Each step lists what we did, what we measured, and which file in
`bench/data/` holds the evidence. Times are relative; the goal was stated up front as
**prefill ≥ 2,000 tok/s and decode stable around 100**, with a 200K+ window, image input,
concurrency and cross-conversation caching.

---

## 1. Start: the published numbers did not reproduce

Radiance single-card (`flashnext-tp1`) publishes ≈85 tok/s and 2,545 tok/s prefill. Our first
runs produced **950–1,330 tok/s prefill** and a decode measurement that disagreed with the
engine's own counter by 3–5× (`baseline.json`, `chunk8192*.json`). Before tuning anything, we
went looking for the reason.

## 2. Root cause: the link, not the engine

`lspci` on the host showed the card's upstream switch port at **`8GT/s (downgraded)`** — the
platform is PCIe 3.0, so the R9700 runs Gen3 x16. A 2 GiB huge-page copy measured **13.8 GB/s**,
identical at 1/2/4 streams. Radiance's design streams expert state from a pinned host pool across
PCIe every decode step, so its published numbers simply do not apply to this link. Details in
[HARDWARE.md](HARDWARE.md).

Also checked and rejected as explanations: Resizable BAR (BIOS has no such option; BAR0 stuck at
256 MB), UPI/NUMA (29 GiB/s — not a bottleneck), CPU ISA (AVX2 only, `avx512vbmi` missing).

## 3. Switch to Strata, then find the one knob that mattered

Strata v0.1.43 HIP build, IQ3_XXS weights (75.8 GiB), 204,800 window. Baseline decode was
**42–52 tok/s** with a static expert tier (`--adapt-every 0`), expert hit rate 64–79%.

Changing to **`--adapt-every 1`** (re-evaluate the expert tier every request):

| | adapt 0 | adapt 1 |
|---|---|---|
| greedy decode | 42.3 | **119.5** |
| 4-way aggregate | 42.9 | **72.3** |
| expert hit rate | 64–79% | **100%** |

Engine log evidence: `adaptive tier: 437 experts swapped in`, then
`routed entries per window: VRAM 98.6% / CPU 1.4%`. Files: `strata-batch4-cache4g.json`,
`strata-adapt1.json`, `strata-adapt1-r2.json`. **This was the single biggest win of the day.**
Cost: sampled output is no longer byte-reproducible.

## 4. Prefill: WMMA and chunk size

`STRATA_HIP_WMMA=1` (with `STRATA_PREFILL_RING=96`) took 15K prefill from **1,709 → 2,336**.
Files: `strata-wmma-off.json`, `strata-wmma-on.json`, `strata-wmma-on-steady.json`. Output is not
bit-identical (greedy diverges after ~50 tokens), which is expected for a different reduction
order.

`--prefill 16384` was tried and **lost**: 1,928 vs 2,336 at 15K (`strata-prefill16k.json`).
8192 stayed.

## 5. hipBLASLt tuning table: a real +28%, but only on the right version

Upstream ships a gfx1201 table for hipBLASLt **1.2.2** (which is what system ROCm 7.2.4 has).
Loading it via `STRATA_HIPBLASLT_TUNING=<path>` and confirming it in the log
(`prefill gemm: hipBLASLt tuning enabled (24 rows, gfx1201, version 100202)`) gave, on a clean
6-bucket matrix:

| Bucket | No table | With table | Gain |
|---|---|---|---|
| 4K | 1,303 | 1,929 | +48% |
| 8K | 1,881 | 2,360 | +25% |
| 16K | 1,915 | 2,405 | +26% |
| 32K | 1,882 | 2,383 | +27% |
| 64K | 1,827 | 2,272 | +24% |
| 128K | 1,672 | 2,043 | +22% |

Files: `matrix-clean-T1-baseline.json` vs `matrix-clean-T3-table.json`. Prefill target of 2,000
was met at every bucket.

## 6. Sampling: we were tuning the wrong variable

We then spent time on temperature and `--spec-min-p`, and most of it was wasted. Measured:

- `--spec-min-p 0.5` vs `0.7`, three different prompts each: **43.6 vs 43.5 tok/s** — zero
  difference, acceptance 64% → 76%. Matches upstream's own "`0.3-0.7` within noise".
  Files `ab-spec-p05.json`, `ab-spec-p07.json`.
- Temperature sweeps produced 42–98 tok/s **for the same prompt and the same temperature**.
  The real variable is the acceptance rate, which follows what the model is writing.

The decisive fact came from upstream docs, not from our guessing: **with no `sampling` block, a
request that omits sampling keys decodes greedily.** Our client sends no temperature, so it was
already on the fast path — and the `--temperature 0.3` we had added was *slowing it down*. We
removed it, then re-added sampling deliberately as a `sampling` block (0.3 / 0.95 / 20) for
determinism in engineering work, and measured the cost: acceptance 72% → 83%, decode 50.2 → 52.4
(`ab-spec-notemp-greedy.json` vs `ab-spec-notemp-t03.json`).

## 7. `--batch 4` vs no batch (the concurrency question)

Same disk, same weights, same window, 4/8/16/32/64/128K input × 2K output, both arms:

| | `--batch 4 --batch-mtp` | no batch |
|---|---|---|
| Concurrency semantics | 4 requests advance **simultaneously** (~18 tok/s each) | **queued**: one at full speed, the rest wait |
| 4-way aggregate | 72.3 | 69.7 |
| Matrix decode mean | 73.4 | 61.5 |
| Expert slots / VRAM | 13,146 / 21.4 GiB | **15,412 / 25.0 GiB** |
| RAM free | ~9 GB | **~16 GB** |
| Session save/restore | **501 — unavailable with batch** | works |

Files: `matrix-A-4to128.json`, `matrix-B-4to128.json`, `strata-A-newpool.json`, `strata-B-arm.json`.

We chose **no batch**, because the 8-slot conversation cache and session persistence were worth
more than 4-way parallelism for this workload. Note the decode column is dominated by acceptance
(63–94%), not by batch — treat ±15% as noise.

## 8. Cross-conversation cache: it works, and here is the matching rule

8 conversations of ~6.4K tokens, 6 GiB / 8 slots, `--conversation-cache-min-tokens 4096`:

| Pass | TTFT |
|---|---|
| Cold, 8 conversations | 4.1 s each (37.7 s total) |
| Round-robin back to them | **0.54 s**, `cached ≈ 6,400`, only 17 tokens re-read, **8/8 hits** |

The rule we had to discover by experiment: a parked snapshot is reused **only when the new prompt
is an exact continuation of the parked state, assistant answer included**. Same opening, different
trailing question → `cached=0`, full re-read. That is exactly the shape an agent harness sends
(it resends the whole history each turn), so it works in practice — but it is not a semantic
cache.

## 9. ROCm 10.1 container: five traps, then a real decode win

Built the engine inside `rocm/dev-ubuntu-24.04:10.1.0-full`. Traps, all recorded in
[reproduce/README.md](../reproduce/README.md):

1. The arch variable is **`CMAKE_HIP_ARCHITECTURES=gfx1201`**, not `GPU_TARGETS` — with the wrong
   one it silently builds gfx1100 and the binary will not load.
2. `docker run --rm` throws away your installed toolchain every time; use a persistent build
   container plus `docker exec`.
3. The engine binary is not an HTTP server — the API comes from `serve/server.py`, so the app and
   its Python deps must be in the image too.
4. Runtime needs `LD_LIBRARY_PATH=/opt/rocm/lib`.
5. A container without `/data` mounted looks like a model bug; commit the prepared container and
   re-run with the mounts.

Compatibility question answered by measurement: ROCm 10.1 user space read
`ROCk module version 6.19.14` and ran fine. **Container isolation covers user space; the kernel
driver is always on the host**, and the KFD ABI check is what would have failed. It did not.

Result — same clean matrix, twice:

| Build | Prefill mean | Decode mean | Decode peak |
|---|---|---|---|
| Host ROCm 7.2.4 + 1.2.2 table | **2,232** | 73.2 | 93 |
| ROCm 10.1 container, no table | 1,955 / 1,943 | **93.3 / 91.5** | **107.8** |

Files: `matrix-clean-RCm10.json`, `matrix-clean-RCm10-r2.json`.

## 10. Calibrating a tuning table for hipBLASLt 1.4.1: 0%

ROCm 10.1 ships hipBLASLt 1.4.1 and upstream ships no gfx1201 table for it, so we calibrated our
own with the engine's `tune_hipblaslt` over 43 GEMM shapes (`tuning/cases.txt` →
`tuning/gfx1201-hipblaslt-100401.txt`), confirmed the load in the log
(`tuning enabled (43 rows, gfx1201, version 100401)`) and re-ran the matrix:
**prefill 1,949 → 1,939, i.e. nothing.** Upstream's own note says exactly this about 1.4.1 on the
R9700. File: `matrix-clean-RCm10-table.json`. The table is published anyway — it is a valid
calibration, and knowing it gains 0% is worth 20 minutes to the next person.

## 11. Image encoder on the GPU: 4×

Upstream's `tools/vision` offers only CPU and CUDA builds (which is why AMD is documented as
CPU-only). We added a HIP path — three lines, `patches/001-vision-hip-gfx1201.patch` — and built
it with ROCm 10.1. Single-image request: **14–16 s → 3.8 s**, same recognition result.

## 12. MTP depth sweep: 4 is the sweet spot

Theory first: tokens per step = `1 + Σ p₁…p_k`, step time ≈ `t₀ + k·t_draft`, so depth only pays
while the conditional acceptance of the next position stays above roughly 0.6. Then measured,
2K context, 1K output, three prompts per depth:

| `--spec` | Decode mean | Acceptance |
|---|---|---|
| **4** | **99.9** | 86% |
| 5 | 73.6 | 72% |
| 6 | 97.3 | 73% |
| 7 | 90.3 | 71% |
| 8 | 80.6 | 61% |

File: `spec-sweep.json`. Matches the theory: acceptance decays with position while step time grows
linearly. Also worth knowing: `/metrics` reports `engine.spec = 6` (verify window rows) and
`engine.mtp_max = 4` (actual depth) — easy to misread.

## 13. Context to 262,144, and where it stops being usable

`--max-context 262144` loaded fine (model trained window is 262,144) with ~20 GB RAM still free.
A 230,062-token prompt: **prefill 1,534, TTFT 149.9 s, decode 56.9** (acceptance 65%). A ~256K
prompt was **rejected with HTTP 400** — the engine refuses rather than truncating. Practical
ceiling ~240–245K, leaving room to generate.

Decode at long context: 100+ (≤32K) → 87 (128K) → 57 (230K). Acceptance at 64K/128K was 80–87%,
the same as short context — so this drop is attention cost plus KV streaming from 64K up, **not**
MTP degradation.

## 14. Autosave and automatic restore, baked into the container

`/opt/strata/autosave.sh` runs from the entrypoint: every 900 s it saves slot 0 to
`/sessions/autosave-N.bin`, rotating 4 copies (`AUTOSAVE_KEEP`), failures silent. The entrypoint
then waits for the API to answer and **restores the newest snapshot** (`AUTOSAVE_RESTORE=1`).

End-to-end test: a 1,863-token conversation → save → `docker restart` (96 s to ready) → continue
the same conversation: **`cache_n=1863`, 18 tokens re-read, TTFT 0.54 s**. Safety test: after a
restore, an unrelated question re-reads from scratch (`cache_n=0`) and answers correctly.

## 15. Final state, and what is still open

Production: container on ROCm 10.1, `strata-hip10:prod`, weights mounted read-only from outside
the image (nothing model-related inside the image), 85 s startup, decode 95–99, prefill
1,900–2,100, images 3.8 s, 8-slot cache hot at 0.54 s, autosave every 15 minutes.

Still open, honestly:
- decode cannot be pinned at 100 — it is content-dependent by construction;
- `--batch` and session save/restore remain mutually exclusive in v0.1.43;
- the tuning table that gives +28% belongs to ROCm 7.2.4, and the build that gives decode 100
  belongs to ROCm 10.1. We have not found a version that gives both.

## 16. Follow-up the next morning (2026-10-27)

Three changes after the record above was written, all small, one of them with a surprise:

1. **Conversation cache raised 8 slots / 6 GiB → 12 slots / 12 GiB**, `min-free` 2048 → 3072,
   driven by real multi-turn usage rather than by a benchmark. Log evidence and the 12-conversation
   probe are in [FINDINGS.md](FINDINGS.md) §6; the probe script is `bench/conv12.py`.
2. **The surprise:** the autosave snapshot went from 237 MB to **2.28 GB**, because parked
   conversations are carried in what slot 0 saves. `AUTOSAVE_KEEP` dropped 4 → 2 for that reason
   alone. Free RAM fell from ~16–20 GB to **13 GiB**.
3. **`python3-pil` added to the image.** Without Pillow the server refuses non-JPEG image input
   with `this image format needs Pillow`; a WebP request failed until it was installed. It is a
   lazy import inside the request handler, so installing it into a running container takes effect
   without a restart — verified with a WebP request that then answered correctly (73 prompt tokens,
   1.78 s prefill).
