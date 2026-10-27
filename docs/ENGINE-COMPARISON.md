# Engine comparison on one card, one context window

Three engines were run on the **same R9700, the same 204,800-token window, the same weights
family** on the same day. This page is about **architecture fit**, not about which project is
better. Two of the three are third-party projects and their published numbers come from
different platforms; we say so explicitly.

Read [HARDWARE.md](HARDWARE.md) §1 first: this machine moves host↔GPU data at **13.8 GB/s**
because the platform is PCIe 3.0 and the link negotiated **Gen3 x16**.

---

## Radiance (single-card `flashnext-tp1`)

**Published figures:** ≈85 tok/s decode, 2,545 tok/s prefill. Those come from **Gen4/Gen5
platforms**. We are not disputing them — we could not reproduce them here, and the reason is
architectural.

**How it works:** a fixed expert working set in VRAM plus a **43 GiB pinned host pool**, with the
n-gram/PLE table (47.68 GiB) on disk. Each decode step routes experts **from host memory across
PCIe** into the compute path.

**What we measured** (`bench/data/baseline.json`, `chunk8192*.json`, `spec7.json`):

| Run | Prefill | Harness-measured decode | Engine counter `decode_tokens_per_second` | Acceptance |
|---|---|---|---|---|
| `baseline` (4K/16K/64K) | 1,324 / 1,226 / 1,301 | 14.2 / 21.5 | 76.8 | 58% |
| `chunk8192` | 990 / 981 / 950 | 13.7 / 27.6 | 126.2 | 43% |
| `chunk8192-r2` | — / 1,129 / 991 | 20.2 / 24.3 / 23.9 | 94.6 | 45% |
| `chunk8192-int8192` | — / 980 / 917 | 14.8 / 25.9 | 138.2 | 46% |
| `spec7` | 1,130 / 1,314 / 1,307 | 10.2 / 16.6 | 75.1 | **22%** |

Two things to take from this table:

1. **Prefill landed at 950–1,330 tok/s**, i.e. about half the published 2,545. That is exactly
   what a 13.8 GB/s link predicts for a design that streams expert state over PCIe.
2. **The harness-measured decode and the engine's own counter disagree by 3–5×.** The engine
   counter measures the decode loop; the harness measures a whole request including routing and
   cache effects. We report both rather than picking the flattering one. Later runs using the
   server's own `timings` block gave 56–63 tok/s at temperature 0.7, which is the number we
   would quote for Radiance on this machine.

**Memory cost:** the 43 GiB pinned pool left only **6–9 GB** of RAM free. That alone made the
8-slot conversation cache impossible to enable, and it is why the 114 GB Radiance model had to be
removed from the pool before the 81 GB Strata weights could be installed.

---

## Strata v0.1.43 (the one we kept)

**How it works:** expert tiering with a VRAM cache, experts resident in RAM and computed on CPU
when not cached, KV in int8 with streaming from RAM beyond ~64K. Nothing is streamed across PCIe
per decode step.

**What we measured** (see [FINDINGS.md](FINDINGS.md) for the full matrices):

| Stage | Prefill | Decode |
|---|---|---|
| Host build, ROCm 7.2.4, no tuning table | 1,747 mean | 58.9 mean |
| Host build + hipBLASLt 1.2.2 tuning table | **2,232 mean** | 73.2 mean |
| ROCm 10.1 container build | 1,940–1,955 mean | **92–93 mean, 108 peak** |
| Production container (final) | 1,187 (2.8K) / 1,772 (11K) / 1,916 (44K) | **96.7 greedy / 97.8 sampled** |

**Why it wins here:** it does not need to move expert state across the 13.8 GB/s link every step.
`--adapt-every 1` keeps the hot experts in VRAM (measured hit rate 100%) and the rest is computed
where the data already is.

**Memory cost:** ~40 GiB of anonymous memory plus page cache. With the original 6 GiB / 8-slot
conversation cache that left **~16–20 GB** free; with the current 12 GiB / 12-slot cache the
container is resident at **58.0 GiB of 72 GiB (79.9%)** and **13 GiB** is available. Enough for
SSD session files, but the headroom is now the thing to watch.

---

## Paiton Flash-Next (vLLM + plugin)

Official figures (258.7 / 687.5 tok/s) are for a **TP2 two-card** configuration with 128 GB+ of
RAM. On a single card it is not a usable configuration, so it was not benchmarked. It is listed
only so the comparison is complete: if you have two cards, it is the option to evaluate.

---

## The decision, stated as a rule

Do not ask "which engine is faster". Ask **"what does this engine move across PCIe per decode
step, and what is my measured link bandwidth?"**

| Engine | Per-step PCIe traffic | On a 13.8 GB/s link | On a Gen5 x16 link |
|---|---|---|---|
| Radiance tp1 | expert state from the pinned host pool | capped | matches its published numbers |
| Strata (adapt-every 1) | none per step (experts resident) | not link-limited | also fine |
| Paiton TP2 | across cards, not over the host link | n/a single card | designed for it |

The same engine family can be the right answer on one machine and the wrong answer on another.
Attach the link width to any engine comparison you read.
