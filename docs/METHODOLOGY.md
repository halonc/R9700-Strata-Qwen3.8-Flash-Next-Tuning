# Measurement methodology

The numbers in this repo are only useful if they are reproducible. This is the discipline we used,
including the parts we got wrong the first time.

## 1. Three guards against cache pollution

Every timed request carries all three:

1. **A fresh random nonce at token 0.** Each prompt starts with `N` plus 8 random letters, so the
   very first token differs from every previous request and no prefix cache can match.
2. **`"strata_checkpoint": false`** in the request body, so a one-off prompt is not parked into the
   conversation cache and cannot speed up the next measurement.
3. **A discarded warm-up request** before timing starts (2K tokens, output thrown away), because
   `--adapt-every 1` builds the expert tier per request.

In the clean matrices this shows up as `cached: 0` on every row. If you see `cached > 0` in a
prefill comparison, the comparison is invalid.

## 2. Never measure the first request after a restart

With an adaptive expert tier the first 1–2 requests run at 45–50 tok/s and the third onward at
90–120. We published one such number by accident (`matrix-B-4to128.json`, 4K bucket, 982 tok/s
prefill) and it is footnoted rather than deleted — the raw JSON is left exactly as measured.

## 3. One variable at a time, and confirm it actually took effect

Every knob change is followed by a log check, because a flag that is silently ignored produces a
perfectly plausible number:

| What we changed | Log line that proves it loaded |
|---|---|
| hipBLASLt tuning table | `prefill gemm: hipBLASLt tuning enabled (43 rows, gfx1201, version 100401)` |
| `--adapt-every 1` | `adaptive tier: 437 experts swapped in`, `routed entries per window: VRAM 98.6% / CPU 1.4%` |
| engine ready / window | `session is up: n_ctx=262144 n_gpu_layers=-1 input_modalities=[text, image]` |
| MTP depth | `GET /metrics` → `engine.mtp_max` |

**Trap:** `/metrics` reports `engine.spec = 6` and `engine.mtp_max = 4`. The first is the number of
rows in the verify window (`1 + spec` plus drafts), the second is the actual MTP depth. Reading
`spec` as the depth will make you think you are running something you are not.

## 4. Acceptance rate is a first-class result, not a footnote

With `--spec 4`, tokens per step = `1 + 4 × acceptance`. Every decode number in `bench/data/` is
recorded next to its acceptance rate, and `spec-sweep.json` additionally stores raw
`drafts` / `accepted` counts so you can recompute it.

The consequence, stated plainly: **decode speed on this machine is 30–108 tok/s depending on what
the model is writing.** Structured text and code sit high, free-form prose sits low. We tried
temperature, `--spec-min-p`, `--coupled-draft`, KV formats and batch sizes; none of them
stabilised acceptance. Only content does. Any comparison that does not attach prompt type, context
length, temperature and build is not comparable.

## 5. Single runs, with known noise

To keep a full day of experiments feasible, most matrix rows are **single runs**. The honest noise
estimate from repeated identical configurations is **±15% on decode** (same config, same prompt,
42–98 tok/s observed) and **±2% on prefill**. Where a decision hinged on a small difference we ran
three different prompts and averaged (`spec-sweep.json`, `ab-spec-*.json`).

## 6. A measurement we threw out

`baseline-decode.json` contains a decode value of **34,169.5 tok/s**. That is a harness artifact
(a zero-length decode window divided by a near-zero duration), not a result. It is kept in
`bench/data/` because we do not edit raw data, and it is excluded from every table. If you write
a parser over these files, filter it.

## 7. Storage benchmarks must bypass ARC

`dd` on a ZFS dataset with a warm ARC reports memory speed, not disk speed: our first run claimed
7.9 GB/s of reads. Correct method: create a temporary dataset with `compression=off` and
`primarycache=none`, then measure. The honest numbers are in [HARDWARE.md](HARDWARE.md) §4.

## 8. Reproducing the headline matrix

```bash
cd bench
python3 matrix_port.py        # 4/8/16/32/64/128K input, 1K output, guards on
python3 sweep_spec.py         # --spec 4..8, restarts the service per depth
python3 conv8.py              # 8-conversation cache, cold vs hot
```

Each script writes its own JSON next to the ones in `bench/data/`.
