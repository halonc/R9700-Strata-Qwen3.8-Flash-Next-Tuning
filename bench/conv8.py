#!/usr/bin/env python3
"""8 条对话轮换 + SSD session 存取：验证跨对话缓存效果。"""
import json, random, string, time, urllib.request

BASE = "http://127.0.0.1:8080"
MID = json.loads(urllib.request.urlopen(BASE + "/v1/models", timeout=10).read())["data"][0]["id"]
W = "系统 推理 缓存 专家 带宽 优化 显存 调度 验证 质量".split()


def post(path, body, timeout=1200):
    r = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"})
    t0 = time.time()
    d = json.loads(urllib.request.urlopen(r, timeout=timeout).read())
    d["_wall"] = time.time() - t0
    return d


def mk(seed, nwords=3500):
    r = random.Random(seed)
    return "N" + "".join(r.choice(string.ascii_lowercase) for _ in range(8)) + " " + " ".join(r.choice(W) for _ in range(nwords))


def chat(p, mt=60):
    return post("/v1/chat/completions", {"model": MID, "max_tokens": mt, "temperature": 0.3,
                                        "messages": [{"role": "user", "content": p}]})


prompts = [mk(i) for i in range(8)]

print("=== 第一轮（全冷）===")
cold = []
t0 = time.time()
for i, p in enumerate(prompts):
    d = chat(p + "\n\n问题一：这段话在讲什么？")
    t = d["timings"]
    cold.append((t.get("prompt_n"), t.get("prompt_ms", 0) / 1000))
    print("  #%d prompt_n=%6s  TTFT %5.1fs" % (i + 1, t.get("prompt_n"), cold[-1][1]))
print("  8 条冷启动总耗时 %.1fs" % (time.time() - t0))

print("=== 第二轮（轮换回来，期望命中缓存）===")
warm = []
for i, p in enumerate(prompts):
    d = chat(p + "\n\n问题二：再具体一点？")
    t = d["timings"]
    warm.append((t.get("prompt_n"), t.get("cache_n"), t.get("prompt_ms", 0) / 1000))
    print("  #%d prompt_n=%6s cached=%6s TTFT %5.1fs" % (i + 1, t.get("prompt_n"), t.get("cache_n"), warm[-1][2]))

print("=== SSD session 文件 ===")
try:
    s = post("/slots/0?action=save", {"filename": "conv-08.bin"})
    print("  save:", {k: s.get(k) for k in ("n_saved", "n_written", "timings")})
    r = post("/slots/0?action=restore", {"filename": "conv-08.bin"})
    print("  restore:", {k: r.get(k) for k in ("n_restored", "n_read", "timings")})
except Exception as e:
    print("  失败:", str(e)[:160])

print("=== 汇总 ===")
print("  冷 TTFT 均值 %.1fs / 热 TTFT 均值 %.1fs" %
      (sum(c[1] for c in cold) / 8, sum(w[2] for w in warm) / 8))
hit = sum(1 for w in warm if (w[1] or 0) > 0)
print("  8 条中命中缓存 %d 条" % hit)
