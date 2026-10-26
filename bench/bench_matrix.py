#!/usr/bin/env python3
"""输入深度矩阵：4K/8K/16K/32K/64K/128K × 2K 输出。"""
import json, os, random, string, time, urllib.request

BASE = "http://127.0.0.1:8080"
LABEL = os.environ.get("LABEL", "run")
DEC = int(os.environ.get("DECODE", "2048"))
MID = json.loads(urllib.request.urlopen(BASE + "/v1/models", timeout=10).read())["data"][0]["id"]
W = "系统 推理 缓存 专家 带宽 优化 显存 调度 验证 质量 索引 队列 拓扑 采样 延迟 吞吐".split()


def mk(ntok):
    r = random.Random(ntok)
    nonce = "M" + "".join(r.choice(string.ascii_lowercase) for _ in range(10))
    nwords = int(ntok / 2.07)        # 实测：每个中文词≈2.07 token
    return nonce + " " + " ".join(r.choice(W) for _ in range(nwords))


def chat(p, mt):
    body = {"model": MID, "max_tokens": mt, "temperature": 0.7,
            "messages": [{"role": "user", "content": p}]}
    r = urllib.request.Request(BASE + "/v1/chat/completions", data=json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"})
    t0 = time.time()
    d = json.loads(urllib.request.urlopen(r, timeout=3600).read())
    return d, time.time() - t0


print("== %s  (2K 输出) model=%s" % (LABEL, MID))
rows = []
for tgt in (4000, 8000, 16000, 32000, 64000, 128000):
    d, wall = chat(mk(tgt), DEC)
    t = d["timings"]
    pn = t.get("prompt_n") or 0
    ttft = t.get("prompt_ms", 0) / 1000
    pp = t.get("prompt_per_second", 0)
    tg = t.get("predicted_per_second", 0)
    acc = (t.get("draft_n_accepted", 0) / t["draft_n"] * 100) if t.get("draft_n") else 0
    out = t.get("predicted_n", 0)
    rows.append({"target": tgt, "prompt_n": pn, "ttft_s": round(ttft, 1), "pp": round(pp),
                 "tg": round(tg, 1), "ms_tok": round(t.get("predicted_per_token_ms", 0), 2),
                 "out": out, "acc": round(acc), "wall": round(wall, 1)})
    print("  in=%3dK  prompt_n=%6d  TTFT %6.1fs  prefill %5d tok/s  decode %6.1f tok/s (%.2f ms)  out=%d  接受%3d%%  wall %5.1fs" %
          (tgt // 1000, pn, ttft, pp, tg, t.get("predicted_per_token_ms", 0), out, acc, wall))
    if wall > 2400:
        print("  (超时保护：跳过更深的档)")
        break

json.dump(rows, open("./data/matrix-%s.json" % LABEL, "w"), indent=1)
print("  saved ./data/matrix-%s.json" % LABEL)
