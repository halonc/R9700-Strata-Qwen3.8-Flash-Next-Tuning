# Benchmarks

Every number quoted anywhere in this repository comes from a script here and its JSON output in
`data/`. The scripts talk to a local OpenAI-compatible endpoint; change `BASE` if your port differs.

```bash
cd bench
python3 matrix_port.py        # the headline 6-bucket matrix
python3 sweep_spec.py         # --spec 4..8 (restarts the service per depth)
python3 conv8.py              # 8-conversation cache: cold vs hot
python3 ab_spec.py            # --spec-min-p 0.5 vs 0.7
python3 ab_notemp.py          # sampling block vs greedy default
python3 stress_strata.py      # long-context stress
```

Scripts read `BASE` (default `http://127.0.0.1:8080`) and write JSON next to the published ones.
`sweep_spec.py` edits the engine config and restarts the service — set `STRATA_CONFIG` and
`COMPOSE_DIR` first, and do not run it against a service you care about.

## Script → data mapping

| Script | Data files | What it measured |
|---|---|---|
| `matrix_port.py` | `matrix-clean-T1-baseline.json`, `matrix-clean-T3-table.json`, `matrix-clean-RCm10.json`, `matrix-clean-RCm10-r2.json`, `matrix-clean-RCm10-table.json` | the clean 4/8/16/32/64/128K matrix across four builds |
| `bench_matrix.py` | `matrix-A-4to128.json`, `matrix-B-4to128.json` | batch-4 vs no-batch A/B |
| `sweep_spec.py` | `spec-sweep.json` | `--spec` 4…8 sweep |
| `ab_spec.py` | `ab-spec-p05.json`, `ab-spec-p07.json` | `--spec-min-p` A/B |
| `ab_notemp.py` | `ab-spec-notemp-greedy.json`, `ab-spec-notemp-t03.json`, `ab-spec-T4-temp03.json` | sampling block vs greedy |
| `conv8.py`, `conv8b.py` | — (results in `docs/TIMELINE.md` §8) | 8-conversation cache, cold vs hot |
| `strata_bench.py` | `strata-*.json` | per-knob A/B: adapt-every, WMMA, prefill chunk, KV format, batch |
| `bench.py`, `pp3.py` | `baseline*.json`, `chunk8192*.json`, `spec7.json` | the **other engine's** morning runs |
| `matrix_clean.py` | `matrix-clean-*.json` | the matrix with cache-pollution guards added |
| `verify_strata.py` | — | config/knob verification probes |

## What is deliberately not in these files

The prompts are **synthetic**: each request starts with a fresh random nonce (`N` plus 8 random
letters) followed by random words from a fixed word list. No real conversation text, no user
content, and no model output is stored anywhere in `data/` — only counters (`pp`, `tg`, `acc`,
`ttft_s`, `out`, `cached`, `wall`, `drafts`, `accepted`).

`data/*.bin` does not exist and must never be created here: session snapshots contain live
conversation KV. `.gitignore` enforces it.

## Known bad measurement

`baseline-decode.json` contains `decode_tps: [15.4, 34169.5]`. The second value is a harness
artifact (a decode window of ~0 length). It is kept unedited and excluded from every table.
