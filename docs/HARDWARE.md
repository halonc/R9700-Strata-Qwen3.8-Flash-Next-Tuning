# Hardware facts that decide the measurements

Everything here was measured on the machine that produced `bench/data/`. Only facts that change
a number are listed; the surrounding virtualisation layout is deliberately omitted.

## 1. The PCIe link is the ceiling: 13.8 GB/s

The host CPU is a Xeon Gold 6252 (Cascade Lake) — **PCIe 3.0**. The R9700 sits behind a PCIe
switch on the board, and the switch's downstream port reports:

```
LnkSta: Speed 8GT/s (downgraded), Width x16
```

i.e. the card negotiates **Gen3 x16**, not Gen4/Gen5.

Measured host↔GPU bandwidth with a 2 GiB huge-page copy:

| Streams | Bandwidth |
|---|---|
| 1 | 13.8 GB/s |
| 2 | 13.8 GB/s |
| 4 | 13.8 GB/s |

Identical at 1/2/4 streams ⇒ this is a **link ceiling**, not contention. Consequence: any engine
whose decode step streams model state across PCIe is capped at roughly

```
13.8 GB/s ÷ (bytes of expert state moved per token)
```

and no amount of tuning inside the engine changes that. This is the single most important number
in this repository — see [docs/ENGINE-COMPARISON.md](ENGINE-COMPARISON.md) for how it decided the
engine choice.

## 2. No Resizable BAR on this platform

The card supports large BARs (BAR0 up to 32 GB) and the firmware already has the >4G decoding
window open, but BAR0 is currently **256 MB**. The platform BIOS (2.50.0) exposes **no Resizable
BAR option** — this is a known limitation of this workstation generation, not a setting we missed.

Practical effect: the engine cannot map the whole framebuffer/weight window through BAR0, which
is another reason a "stream weights over PCIe" design is not viable here.

## 3. CPU and memory are not the bottleneck

| Measurement | Result |
|---|---|
| Cross-socket (UPI) DRAM read, 8 threads | **29 GiB/s** |
| Memory available to the engine at 262K context | **~20 GB free** |
| CPU ISA floor | AVX2 only — this CPU lacks `avx512vbmi`, so the engine's AVX-512 expert kernels are unavailable and cannot be re-enabled by rebuilding |

The AVX2-only expert path is a fixed property of the platform. It matters because Strata computes
some experts on CPU: it is fast enough here, but it is AVX2-fast, not AVX-512-fast.

## 4. Storage: a two-disk ZFS stripe, measured with ARC bypassed

Measured on a temporary dataset with `compression=off` and `primarycache=none` (without that flag
ZFS ARC serves the reads and the numbers are fiction — an early run produced a fake 7.9 GB/s):

| Test | Result |
|---|---|
| Sequential write, 4 GB | **431 MB/s** |
| Sequential read, 4 GB | **690 MB/s** |
| 4K random read (8 threads, qd16) | **6.7k IOPS** (26 MB/s) |
| 4K random write | **21k IOPS** (82 MB/s) |
| Through the guest's virtio disk, 2 GB write / read | **644 / 521 MB/s** |

Reads add up (690 ≈ 2 × 345); writes only reach 431 MB/s. The limit is the onboard SATA controller
plus ZFS synchronous write, not the disks.

What this changed in practice: session save went from **~50 MB/s** (previous mirrored pool, 92%
full, virtual disk) to **~120 MB/s**, and restore to **~850 MB/s**.

## 5. NVMe: measured, then deliberately not installed

A 256 GB NVMe drive was available. The onboard M.2 slots sit behind an Intel VMD domain with no
device populated, and the free physical slot is x4. Expected gain was startup 215 s → ~100 s and
session save 2.6 s → ~1 s. **256 GB is too small to hold the 76 GiB of weights plus sessions**,
so the drive was not installed and the stripe pool stayed. Startup is 85 s anyway once the page
cache is warm.

## 6. Why "upgrade the host driver" is a no-op here

```
driver bound to the R9700 on the host:   vfio-pci
amdgpu modules loaded on the host:       0
```

With the card passed through, the host only hands the device to the guest. The driver that
actually serves inference lives in the guest (`amdgpu 6.19.14`, DKMS-built). ROCm **10.1** user
space was verified to pass the KFD ABI check against that driver and produced the numbers in
[this repo](FINDINGS.md) — so the "new user space needs a new kernel driver" worry is already
answered by measurement. A host kernel/driver change would buy 0–3% at best and would risk the
passthrough. We did not do it.

## 7. Power and clocks

Under sustained load the core clock holds **3079 MHz** while board power sits at **97–122 W**.
The card is latency-bound, not power-limited: it is not throttling, it is waiting. That is
consistent with §1 — the bottleneck is data movement, not FLOPs.
