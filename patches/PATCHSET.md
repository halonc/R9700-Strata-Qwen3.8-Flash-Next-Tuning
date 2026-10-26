# Patch set

**Baseline:** Strata tag **`v0.1.43`** (upstream commit `7695859aa13afb248bdb4d36f9b2e95707db079d`,
2026-10-11). Note that a checkout directory named `src-v0.1.40` can still contain tag `v0.1.43` —
check with `git describe --tags` before applying anything.

The engine itself is **unpatched**. Everything below is in `tools/vision`.

---

## 001-vision-hip-gfx1201.patch — give the image encoder a HIP path

**Why.** Upstream's `tools/vision/CMakeLists.txt` exposes exactly two build flavours: portable CPU
and `STRATA_VISION_CUDA=ON`. There is no AMD path, which is why the docs say the image encoder is
CPU-only on AMD GPUs. On this machine that cost **14–16 s per image request**.

**What it does.** Three lines after the existing backend selection:

```cmake
set(GGML_HIP ON CACHE BOOL "" FORCE)
set(AMDGPU_TARGETS gfx1201 CACHE STRING "" FORCE)
set(GPU_TARGETS gfx1201 CACHE STRING "" FORCE)
```

`tools/vision` builds llama.cpp as a subdirectory (`add_subdirectory(${LLAMA_DIR} llama)`), so
forcing `GGML_HIP` there selects `ggml-hip` for the `mtmd` encoder. No source file is touched —
`strata_vision.cpp` is unchanged.

**Apply and build.**

```bash
git clone <strata-upstream> src && cd src && git checkout v0.1.43
patch -p1 < ../patches/001-vision-hip-gfx1201.patch

cmake -S tools/vision -B build-vision -G Ninja -DCMAKE_BUILD_TYPE=Release \
      -DLLAMA_DIR=$PWD/third_party/llama.cpp -DSTRATA_PORTABLE=OFF
cmake --build build-vision --target strata-vision
```

`LLAMA_DIR` must point at a real llama.cpp checkout; the engine build fetches one into
`_deps/strata_llamacpp-src`, and reusing it is what we did.

**Result.** Single image request **14–16 s → 3.8 s**, identical recognition output.

**Caveats.**

- `AMDGPU_TARGETS` must match your card. `gfx1201` is the R9700; a different RDNA3 card needs its
  own target, and a wrong target builds a binary that fails to load.
- This is a build-configuration change, not an upstream-supported feature. If upstream later adds
  an official AMD option, prefer that and drop this patch.
- The encoder now needs the ROCm runtime at execution time, so it must run inside the same
  container (or on a host with the matching `/opt/rocm`) as the engine.
