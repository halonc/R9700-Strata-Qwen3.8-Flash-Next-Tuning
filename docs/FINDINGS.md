# Findings: every measured matrix

All tables below are generated from `bench/data/*.json`. Each table names its source file.
Unless stated otherwise: **Strata v0.1.43, IQ3_XXS 176B MoE, single R9700, 1K output,
`sampling.temperature 0.3`, cache-pollution guards on** (see [METHODOLOGY.md](METHODOLOGY.md)).

---

## 1. The clean matrix: four builds, six context buckets

Prompt length → prefill (tok/s):

| Input | host ROCm 7.2.4, no table | host 7.2.4 + hipBLASLt 1.2.2 table | ROCm 10.1, run 1 | ROCm 10.1, run 2 | ROCm 10.1 + our 1.4.1 table |
|---|---|---|---|---|---|
| 4K | 1,303 | **1,929** | 1,602 | 1,578 | 1,563 |
| 8K | 1,881 | **2,360** | 2,074 | 2,045 | 2,045 |
| 16K | 1,915 | **2,405** | 2,136 | 2,117 | 2,118 |
| 32K | 1,882 | **2,383** | 2,106 | 2,104 | 2,102 |
| 64K | 1,827 | **2,272** | 2,007 | 2,006 | 2,005 |
| 128K | 1,672 | **2,043** | 1,802 | 1,808 | 1,799 |
| **mean** | 1,747 | **2,232** | 1,955 | 1,943 | 1,939 |

Time to first token (seconds):

| Input | no table | 1.2.2 table | ROCm 10.1 r1 | ROCm 10.1 r2 | ROCm 10.1 + table |
|---|---|---|---|---|---|
| 4K | 3.1 | 2.1 | 2.5 | 2.6 | 2.6 |
| 16K | 8.4 | 6.6 | 7.5 | 7.6 | 7.5 |
| 64K | 34.9 | 28.1 | 31.8 | 31.8 | 31.8 |
| 128K | 76.3 | 62.5 | 70.8 | 70.5 | 70.9 |

Decode (tok/s) — same prompts, same runs:

| Input | no table | 1.2.2 table | ROCm 10.1 r1 | ROCm 10.1 r2 | ROCm 10.1 + table |
|---|---|---|---|---|---|
| 4K | 52.5 | 59.6 | **100.7** | **107.8** | **106.2** |
| 8K | 48.8 | 77.0 | **103.5** | 65.5 | **104.1** |
| 16K | 84.0 | 51.0 | **103.5** | 99.1 | 64.1 |
| 32K | 30.6 | 93.4 | 77.5 | **101.3** | **101.4** |
| 64K | 53.2 | 81.6 | 87.1 | 87.2 | 64.3 |
| 128K | 83.9 | 76.8 | 87.2 | 87.8 | 63.8 |
| **mean** | 58.8 | 73.2 | **93.2** | **91.5** | 84.0 |
| **peak** | 84.0 | 93.4 | 103.5 | **107.8** | 106.2 |

Sources: `matrix-clean-T1-baseline.json`, `matrix-clean-T3-table.json`,
`matrix-clean-RCm10.json`, `matrix-clean-RCm10-r2.json`, `matrix-clean-RCm10-table.json`.

**Read the decode column with the acceptance rate attached** (it is in the JSON): 60% acceptance
→ 30.6 tok/s, 93% → 93.4 tok/s, in the *same* run. The ROCm 10.1 builds are not faster because
they are cleverer; they hold acceptance higher on these prompts (80–93% vs 60–88%).

---

## 2. Knob-by-knob A/B (host build, ROCm 7.2.4)

Prefill at ~15K / ~55K tokens, decode mean at temperature 0 (greedy) and 0.7, 4-way aggregate:

| Configuration | Prefill 15K / 55K | Decode greedy / sampled | 4-way agg | File |
|---|---|---|---|---|
| `--adapt-every 0`, batch 4 | — | 42.3 / 39.0 | 42.9 | `strata-batch4-cache4g.json` |
| **`--adapt-every 1`**, batch 4 | 1,594 | **89.8 / 62.0** | 71.9 | `strata-adapt1.json` |
| **`--adapt-every 1`**, batch 4, rerun | — | **119.5 / 100.1** | **72.3** | `strata-adapt1-r2.json` |
| WMMA off | 1,709 / 2,187 | 52.5 / 47.7 | — | `strata-wmma-off.json` |
| **WMMA on** (steady) | **2,336** / 2,250 | 59.8 / 62.6 | 41.5 | `strata-wmma-on-steady.json` |
| `--prefill 16384` | 1,928 / 2,263 | 49.4 / 52.9 | 41.4 | `strata-prefill16k.json` |
| `--kv k8v4`, batch 4 | 1,273 / 1,449 | 55.0 / 51.4 | 35.3 | `strata-k8v4-batch4.json` |
| `--kv int8`, batch 2 | 1,662 / 2,134 | 44.0 / 41.7 | 35.3 | `strata-int8-batch2.json` |
| **no batch** + SSD session | 1,708 / 1,839 | **102.9 / 82.8** | 69.7 | `strata-nobatch-ssd.json` |
| batch 4, new pool (rerun) | 1,664 / 2,062 | 83.2 / 78.3 | 72.3 | `strata-A-newpool.json` |
| no batch, new pool | 1,774 / 1,778 | **122.0 / 82.8** | — | `strata-B-arm.json` |
| **production (ROCm 10.1)** | 1,187 (2.8K) / 1,772 (11K) / 1,916 (44K) | **96.7 / 97.8** | — | `strata-ProdRCm10.json` |

Note the pattern: **batch costs single-stream decode** (42–83 vs 100–122) and buys simultaneous
progress; `--adapt-every 1` is worth more than either.

---

## 3. MTP depth sweep (`--spec` 4…8)

2K context, 1K output, three different prompts per depth, service restarted per depth (80 s boot).
Source: `spec-sweep.json`.

| `--spec` | tokens/step | ms/token | Acceptance | Decode mean |
|---|---|---|---|---|
| **4** | 1+4×0.86 ≈ 4.4 | **9.3–11.4** | **86%** | **99.9** |
| 5 | 1+5×0.72 ≈ 4.6 | 11.3–15.2 | 72% | 73.6 |
| 6 | 1+6×0.73 ≈ 5.4 | 9.5–11.5 | 73% | 97.3 |
| 7 | 1+7×0.71 ≈ 6.0 | 9.9–14.0 | 71% | 90.3 |
| 8 | 1+8×0.61 ≈ 5.9 | 12.0–13.2 | 61% | 80.6 |

The JSON also carries raw `drafts` / `accepted` counts per run (e.g. spec 4: 849 drafts, 736
accepted) so you can recompute acceptance yourself.

Earlier, on a different engine, `--spec 7` collapsed acceptance to **22%** and step time to
85 ms (`spec7.json`) — the same decay, more violently.

---

## 4. Sampling: what a `sampling` block actually costs

Three different prompts (code / config-troubleshooting / technical prose), 1K output.

| Configuration | code | config | prose | mean | Acceptance | File |
|---|---|---|---|---|---|---|
| no `sampling` block (request omits temperature → greedy) | 47.6 | 53.3 | 49.7 | 50.2 | 72% | `ab-spec-notemp-greedy.json` |
| `sampling.temperature 0.3` | 53.2 | 59.4 | 44.7 | 52.4 | 83% | `ab-spec-notemp-t03.json` |
| `sampling.temperature 0.3`, rerun | 43.4 | 46.0 | 91.0 | 60.1 | 72% | `ab-spec-T4-temp03.json` |
| `--spec-min-p 0.5` | 42.2 | 47.5 | 41.1 | 43.6 | 64% | `ab-spec-p05.json` |
| `--spec-min-p 0.7` | 42.3 | 45.7 | 42.5 | 43.5 | 76% | `ab-spec-p07.json` |

Two conclusions:

- `--spec-min-p` 0.5 → 0.7 raises acceptance by 12 points and changes throughput by **0.1 tok/s**.
  Upstream's "within noise" is exactly right.
- The prose row in `ab-spec-T4-temp03.json` (91.0) versus the same config's other runs is the
  clearest evidence in this repo that **content, not configuration, sets decode speed**.

---

## 5. Long context

| Context | Prefill | TTFT | Decode | Acceptance |
|---|---|---|---|---|
| 128K | 1,802–1,808 | 70.5–70.8 s | 87.2–87.8 | 84–87% |
| 230,062 tokens | **1,534** | **149.9 s** | **56.9** | 65% |
| ~256K tokens | — | — | — | **HTTP 400, request rejected** |

`--max-context 262144` loads and leaves ~20 GB RAM free. The engine refuses an oversized prompt
rather than truncating it, so budget ~240–245K input plus your output.

Decode at 64K and 128K measured **80–87% acceptance**, the same band as 4K–32K. The long-context
decode drop is attention cost plus KV streaming (Strata keeps only the most-read KV resident past
~64K and streams the rest from RAM), **not** speculative-decoding degradation.

---

## 6. Conversation cache and session files

Two different mechanisms; both measured.

**RAM conversation cache**, measured at `--conversation-cache-mib 6144
--conversation-cache-slots 8 --conversation-cache-min-tokens 4096`, 8 conversations of ~6.4K
tokens (the setting has since been raised — see the follow-up below):

| Pass | TTFT | Cached tokens |
|---|---|---|
| Cold, 8 conversations | 4.1 s each (37.7 s total) | 0 |
| Round-robin back | **0.54 s** | ≈6,400 (17 tokens re-read) |
| Hit rate | **8/8** | engine log: `parked=8 bytes=2802377480 evictions=0→7` |

Matching rule, established by controlled probe: a snapshot is reused **only if the new prompt is
an exact continuation of the parked state, including the assistant's answer**. Same opening with a
different trailing question → `cached=0`, full re-read.

**Follow-up, 2026-10-27: the cache was raised to 12 slots / 12 GiB**
(`--conversation-cache-min-free-mib` 2048 → 3072), with a 12-conversation multi-turn probe
(`bench/conv12.py`). Engine log from that day:

| Log line | Reading |
|---|---|
| `parked 135513 tokens in 164.8 ms` | parking a 135K-token window costs **0.16 s** |
| `parked 133858 tokens in 539.5 ms` | worst case seen: **0.54 s** |
| `parked=4 bytes=10988839548 evictions=17` | **4 conversations parked, 11.0 GB of the 12 GiB budget** |
| `restored 20640 tokens (checkpoint) in 93.5 ms` | checkpoint restore is **0.09–0.42 s** |
| `skip parking (192 tokens, below the 4096 minimum)` | the `min-tokens` floor is enforced |

Host memory with the 12 GiB cache in place: 72 GiB total, container resident **58.0 GiB (79.9%)**,
**13 GiB available**. That is the cost of the bigger cache — the 8-slot setting left roughly
16–20 GB free.

**Consequence nobody predicted: the session snapshot grew 10×.** The autosave file went from
237 MB to **2.28 GB** per copy, because the parked conversations are part of what slot 0 saves.
`AUTOSAVE_KEEP` was therefore cut from 4 to 2 (4 × 2.28 GB is 9.1 GB of rotating disk for no
extra safety). The 2.6 s save / 0.4 s restore figures above were measured on a 237 MB snapshot
and have **not** been re-measured at 2.28 GB — expect roughly 10× on the save side.

**Session files** (`/slots/0?action=save|restore`, requires batch off):

| Operation | Size | Time | Throughput |
|---|---|---|---|
| Save | 237 MB | **2.6 s** | ~120 MB/s |
| Restore | 237 MB | **0.4 s** | ~850 MB/s |
| Survive `docker restart` | yes | 96 s to ready | — |
| Continue the restored conversation | `cache_n=1863`, **18 tokens re-read**, TTFT **0.54 s** | | |
| Send an unrelated conversation after a restore | `cache_n=0`, correct answer | | |

---

## 7. Concurrency semantics: `--batch 4` versus no batch

Same pool, same weights, same window, 4/8/16/32/64/128K input × 2K output, temperature 0.7.
Sources: `matrix-A-4to128.json` (batch 4), `matrix-B-4to128.json` (no batch).

| Input | batch 4 prefill / decode | no batch prefill / decode |
|---|---|---|
| 4K | 1,447 / 90.1 | 982¹ / 74.6 |
| 8K | 2,087 / 93.2 | 2,107 / 58.0 |
| 16K | 2,157 / 87.2 | 2,229 / 50.6 |
| 32K | 2,137 / 48.7 | 1,820 / 85.1 |
| 64K | 2,040 / 78.5 | 1,793 / 47.7 |
| 128K | 1,837 / 42.8 | 1,778 / 52.8 |
| **mean** | **1,950 / 73.4** | 1,785² / 61.5 |

¹ first request after a restart — the adaptive tier was still warming up.
² excluding that cold bucket: 1,945.

Structural differences, which matter more than the speed columns:

| | `--batch 4 --batch-mtp` | no batch |
|---|---|---|
| Semantics | 4 requests advance **at the same time** (~18 tok/s each) | **queued**: one at full speed, others wait |
| 4-way aggregate | 72.3 tok/s | 69.7 tok/s |
| Expert slots / VRAM | 13,146 / 21.4 GiB | **15,412 / 25.0 GiB** |
| RAM free | ~9 GB | **~16 GB** |
| Session save/restore | **HTTP 501 — unavailable with batch** | works |
| 8-slot conversation cache | works (hot 0.37 s) | works (hot 0.54 s) |

We run **no batch**: the extra 2,266 expert slots, 7 GB more free RAM and working session files
outweigh simultaneous progress for a single primary user with a cache-heavy agent harness.
