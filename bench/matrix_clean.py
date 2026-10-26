#!/usr/bin/env python3
"""干净矩阵：4/8/16/32/64/128K 输入 × 1K 输出。
防污染：唯一 nonce + strata_checkpoint=false + 先发预热请求丢弃。"""
import json, os, random, string, time, urllib.request

BASE = "http://127.0.0.1:8080"
LABEL = os.environ.get("LABEL", "run")
DEC = int(os.environ.get("DECODE", "1024"))
MID = json.loads(urllib.request.urlopen(BASE + "/v1/models", timeout=10).read())["data"][0]["id"]
W = "系统 推理 缓存 专家 带宽 优化 显存 调度 验证 质量 索引 队列 拓扑 采样 延迟 吞吐".split()


def mk(ntok):
    r = random.Random()
    nonce = "Z" + "".join(r.choice(string.ascii_lowercase + string.digits) for _ in range(14))
    nwords = max(10, int(ntok / 2.07))
    return nonce + " " + " ".join(r.choice(W) for _ in range(nwords))


def chat(p, mt):
    body = {"model": MID, "max_tokens": mt, "messages": [{"role": "user", "content": p}],
            "strata_checkpoint": False}
    r = urllib.request.Request(BASE + "/v1/chat/completions", data=json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"})
    t0 = time.time()
    d = json.loads(urllib.request.urlopen(r, timeout=3600).read())
    return d, time.time() - t0


print("== %s | %dK 输出档 | model=%s" % (LABEL, DEC // 1024, MID), flush=True)
# 预热（丢弃）
chat(mk(2000), 64)
print("  预热完成", flush=True)

rows = []
for tgt in (4000, 8000, 16000, 32000, 64000, 128000):
    d, wall = chat(mk(tgt), DEC)
    t = d["timings"]
    acc = (t.get("draft_n_accepted", 0) / t["draft_n"] * 100) if t.get("draft_n") else 0
    row = {"target": tgt, "prompt_n": t.get("prompt_n"), "ttft_s": round(t.get("prompt_ms", 0) / 1000, 1),
           "pp": round(t.get("prompt_per_second", 0)), "tg": round(t.get("predicted_per_second", 0), 1),
           "out": t.get("predicted_n"), "acc": round(acc), "cached": t.get("cache_n"), "wall": round(wall, 1)}
    rows.append(row)
    print("  in=%3dK prompt_n=%6d cached=%4s TTFT %6.1fs PP %5d TG %6.1f out=%4d 接受%3d%%" %
          (tgt // 1000, row["prompt_n"], row["cached"], row["ttft_s"], row["pp"], row["tg"], row["out"], row["acc"]), flush=True)

json.dump(rows, open("./data/matrix-clean-%s.json" % LABEL, "w"), indent=1)
print("  saved matrix-clean-%s.json" % LABEL)
