#!/usr/bin/env python3
"""MTP 深度扫描：spec 4..8，短上下文（2K）3 段不同输入，1K 输出。"""
import json, os, random, string, subprocess, time, urllib.request

CFG = os.environ.get("STRATA_CONFIG", "./strata-final.json")
BASE = "http://127.0.0.1:8080"
W = "系统 推理 缓存 专家 带宽 优化 显存 调度 验证 质量".split()
OUT = "./data/spec-sweep.json"


def set_spec(s, max_ctx=262144):
    d = json.load(open(CFG))
    a = d["args"]
    a[a.index("--spec") + 1] = str(s)
    a[a.index("--max-context") + 1] = str(max_ctx)
    json.dump(d, open(CFG, "w"), indent=1, ensure_ascii=False)


def restart():
    subprocess.run(["docker", "compose", "restart"], cwd=os.environ.get("COMPOSE_DIR", "."),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait_ready(timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            d = json.loads(urllib.request.urlopen(BASE + "/v1/models", timeout=4).read())
            if d["data"]:
                return time.time() - t0
        except Exception:
            pass
        time.sleep(5)
    raise RuntimeError("not ready")


def mk(nwords, seed):
    r = random.Random(seed)
    return "Q%d" % seed + "".join(r.choice(string.ascii_lowercase) for _ in range(8)) + " " + " ".join(r.choice(W) for _ in range(nwords))


def chat(prompt, mt=1024):
    body = {"model": MID, "max_tokens": mt, "messages": [{"role": "user", "content": prompt}],
            "strata_checkpoint": False}
    r = urllib.request.Request(BASE + "/v1/chat/completions", data=json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(r, timeout=1200).read())
    return d["timings"]


results = {}
for s in (4, 5, 6, 7, 8):
    set_spec(s)
    restart()
    boot = wait_ready()
    MID = json.loads(urllib.request.urlopen(BASE + "/v1/models", timeout=10).read())["data"][0]["id"]
    chat(mk(800, 900), 64)  # 预热，丢弃
    rows = []
    for i in range(3):
        t = chat(mk(1000, 100 + i))          # ~2K token 上下文
        acc = (t.get("draft_n_accepted", 0) / t["draft_n"] * 100) if t.get("draft_n") else 0
        rows.append({"tg": round(t.get("predicted_per_second", 0), 1),
                     "ms_tok": round(t.get("predicted_per_token_ms", 0), 2),
                     "acc": round(acc), "out": t.get("predicted_n"),
                     "drafts": t.get("draft_n"), "accepted": t.get("draft_n_accepted")})
    avg_tg = sum(r["tg"] for r in rows) / 3
    avg_acc = sum(r["acc"] for r in rows) / 3
    results[s] = {"boot_s": round(boot), "rows": rows, "avg_tg": round(avg_tg, 1), "avg_acc": round(avg_acc)}
    print("spec=%d  boot %3ds  TG %6.1f 接受 %3.0f%%  (逐次 %s)" %
          (s, boot, avg_tg, avg_acc, [r["tg"] for r in rows]), flush=True)

json.dump(results, open(OUT, "w"), indent=1)
print("saved", OUT)
