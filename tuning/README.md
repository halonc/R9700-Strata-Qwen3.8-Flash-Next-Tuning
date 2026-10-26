# hipBLASLt tuning tables

## The short version

| hipBLASLt version | Where it lives | Tuning table | Measured effect on prefill |
|---|---|---|---|
| **1.2.2** | system ROCm **7.2.4** | upstream `gfx1201-hipblaslt-100202.txt` | **+22% to +48%** (matrix mean 1,747 → 2,232) |
| **1.4.1** | ROCm **10.1** container | `gfx1201-hipblaslt-100401.txt` (calibrated by us) | **0%** (1,949 → 1,939) |

Tables are scoped to a hipBLASLt version *and* a device architecture — the header line says both:

```
STRATA_HIPBLASLT_TUNING_V1 gfx1201 100401
```

A table whose header does not match the runtime is not applied. That is why the 1.2.2 table gave a
big win on ROCm 7.2.4 and nothing on ROCm 10.1.

## Calibrating a table (this is how ours was made)

The engine ships a calibrator, `tune_hipblaslt`:

```
Usage: tune_hipblaslt [--workspace-mib N] [--shape T,N,K]... [--case dtype,T,N,K,ldy]...
                      [--shapes-file PATH [--tokens T1,T2,...]] [--tuning-out PATH]
Defaults: original three shapes, f16+bf16, T=8192, workspace=32 MiB.
```

We fed it the GEMM shapes taken from the upstream gfx1100 table (43 cases, kept in `cases.txt`)
and wrote the result out:

```bash
docker exec <build> /build/tune_hipblaslt \
    --case-file /build/cases.txt \
    --tuning-out /build/gfx1201-hipblaslt-100401.txt
```

Two practical notes from doing it:

- Passing the cases as a shell-expanded list is fragile — an `awk`-generated list got expanded by
  the outer shell, the calibrator silently ran only its 3 default shapes, and produced a 3-row
  table. Put the cases in a file.
- The calibrator dies if the GPU is busy. Free VRAM first (a zombie calibrator leaves no output
  file, which looks like a success if you only check the exit path).

## Using a table

```bash
STRATA_HIPBLASLT_TUNING=/path/to/gfx1201-hipblaslt-100401.txt
```

Then **verify it loaded** in the engine log:

```
prefill gemm: hipBLASLt tuning enabled (43 rows, gfx1201, version 100401)
```

No such line means the table was not applied — usually a version/arch mismatch, not a slow GPU.

## Why publish a table that gained 0%

Because the useful result is the negative one, and it took 20 minutes to establish. Upstream says
of the R9700 at hipBLASLt 1.4.1:

> a table calibrated on the R9700 at the engine's shapes with that version changed the end-to-end
> prompt speed by 0-3%, within noise, so none was shipped for it: there the plain hipBLAS path is
> already close

Our calibration independently reproduced that. If you are on ROCm 10.x, do not plan your week
around a tuning table; if you are on ROCm 7.2.4 / hipBLASLt 1.2.2, the upstream table is the
cheapest prefill win available.
