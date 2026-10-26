# Already tested, did not help

Check this table before spending an evening on a knob. Every row is a measurement on this machine,
with the file that proves it.

| Knob | Expected | Measured | Verdict | Evidence |
|---|---|---|---|---|
| `--spec 5` | +10% decode | **73.6** vs 99.9 at spec 4 | **worse** | `spec-sweep.json` |
| `--spec 6` | +18% decode | 97.3 vs 99.9 | no gain | `spec-sweep.json` |
| `--spec 7` / `8` | more | 90.3 / 80.6, acceptance 71% / 61% | **worse** | `spec-sweep.json` |
| `--spec 7` (other engine) | more | acceptance **22%**, step 85 ms | collapse | `spec7.json` |
| `--spec-min-p 0.7` | better verify economy | 43.5 vs 43.6 tok/s, acceptance +12 pts | **no effect** | `ab-spec-p05.json`, `ab-spec-p07.json` |
| `--prefill 16384` | faster long prefill | 1,928 vs 2,336 at 15K | **worse** | `strata-prefill16k.json` |
| `--kv k8v4` | cheaper KV, faster long context | 1,273 / 1,449 vs 1,662 / 2,134 int8 | **worse** | `strata-k8v4-batch4.json` |
| `--kv q4_0` | cheaper KV | slower than int8 at 55K | **worse** | host build, reverted |
| `--coupled-draft` | better drafts | acceptance went **down** at low temperature | reverted | host build |
| `--batch 2` | concurrency without batch-4 cost | 4-way agg 35.3, decode 44.0 | not worth it | `strata-int8-batch2.json` |
| `--temperature 0.3` as an engine flag | faster | **slower than the default** | reverted; use a `sampling` block instead | §6 of [TIMELINE.md](TIMELINE.md) |
| hipBLASLt table on **ROCm 10.1** (1.4.1) | +20–40% prefill | **1,949 → 1,939 (0%)** | no effect | `matrix-clean-RCm10-table.json` |
| Calibrating our own 1.4.1 table | recovers the ROCm-10 prefill gap | 43 shapes calibrated, table confirmed loaded, **0% gain** | no effect | `tuning/README.md` |
| Upgrading the host GPU driver | better GPU throughput | host binds `vfio-pci`, loads **0** amdgpu modules | **cannot help**; risk to passthrough | [HARDWARE.md](HARDWARE.md) §6 |
| Resizable BAR | bigger BAR window | BIOS 2.50.0 has **no such option**, BAR0 stuck at 256 MB | not available | [HARDWARE.md](HARDWARE.md) §2 |
| NVMe for `/data` | startup 215→100 s | 256 GB cannot hold 76 GiB weights + sessions | not installed | [HARDWARE.md](HARDWARE.md) §5 |
| AVX-512 expert kernels | faster CPU experts | CPU lacks `avx512vbmi`; rebuild cannot add it | not available | [HARDWARE.md](HARDWARE.md) §3 |
| Docker as a speed trick | containers are faster | container is user space only; the win came from **ROCm 10.1's** libraries, not from isolation | framing matters | [TIMELINE.md](TIMELINE.md) §9 |

---

## The three things that *did* help, for contrast

| Change | Effect |
|---|---|
| `--adapt-every 1` | decode 42 → 100–122, expert hit rate 100% |
| `STRATA_HIP_WMMA=1` + `STRATA_PREFILL_RING=96` | prefill +37% at 15K |
| hipBLASLt 1.2.2 tuning table **on ROCm 7.2.4** | prefill +22% to +48% |
| ROCm 10.1 build | decode mean 73 → 92–93, peak 108 |
| HIP image encoder patch | image request 14–16 s → 3.8 s |

---

## Two traps that are not knobs

1. **The first 1–2 requests after a restart are not measurements.** With `--adapt-every 1` the
   expert tier warms up per request; we repeatedly saw 45–50 tok/s on the first shot and 90–120
   from the third. One published row in `matrix-B-4to128.json` (982 tok/s prefill at 4K) is
   exactly this artifact. Warm up with a throwaway request, then measure.
2. **A scratch `dd` on ZFS measures your ARC, not your disks.** Our first storage benchmark
   reported 7.9 GB/s of reads. Re-run with `primarycache=none` on a temporary dataset and the
   honest number was 690 MB/s.
