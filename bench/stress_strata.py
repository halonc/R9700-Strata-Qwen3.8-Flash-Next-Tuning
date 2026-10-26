#!/usr/bin/env python3
"""并发 / 跨对话缓存 / SSD session 文件 三项压力测试。"""
import json, random, string, statistics, threading, time, urllib.request

BASE = "http://127.0.0.1:8080"
MID = json.loads(urllib.request.urlopen(BASE + "/v1/models", timeout=10).read())["data"][0]["id"]
W = "系统 推理 缓存 专家 带宽 优化 显存 调度 验证 质量 索引 队列".split()


def post(path, body, timeout=1800):
    r = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"})
    t0 = time.time()
    d = json.loads(urllib.request.urlopen(r, timeout=timeout).read())
    d["_wall"] = time.time() - t0
    return d


def prompt(nwords, seed=None):
    r = random.Random(seed)
    nonce = "N" + "".join(r.choice(string.ascii_lowercase) for _ in range(10))
    return nonce + " " + " ".join(r.choice(W) for _ in range(nwords))


def chat(p, maxtok=150, temp=0.7):
    return post("/v1/chat/completions", {"model": MID, "max_tokens": maxtok, "temperature": temp,
                                        "messages": [{"role": "user", "content": p}]})


def ttft(d):
    return d.get("timings", {}).get("prompt_ms", 0) / 1000


print("=== 1) 8 路并发（batch 4，8 客户端）===")
outs = [None] * 8


def one(i):
    d = chat(prompt(1200), 120)
    t = d.get("timings", {})
    outs[i] = t.get("predicted_n", 0)


t0 = time.time()
th = [threading.Thread(target=one, args=(i,)) for i in range(8)]
[x.start() for x in th]
[x.join() for x in th]
wall = time.time() - t0
tot = sum(o for o in outs if o)
print("  8 客户端: 输出 %d tok / %.1fs -> 聚合 %.1f tok/s" % (tot, wall, tot / wall))

print("=== 2) 跨对话缓存（8 槽，finer checkpoint）===")
A = prompt(60000, 1)
B = prompt(8000, 2)
d1 = chat(A + "\n\n问题一：这段在讲什么？", 100)
print("  A 冷: prompt_n=%s ttft=%.1fs" % (d1["timings"].get("prompt_n"), ttft(d1)))
d2 = chat(B + "\n\n问题：讲什么？", 100)
print("  B  : prompt_n=%s ttft=%.1fs" % (d2["timings"].get("prompt_n"), ttft(d2)))
d3 = chat(A + "\n\n问题二：再具体点？", 100)
t = d3["timings"]
print("  A 再: prompt_n=%s cached=%s ttft=%.1fs decode=%.1f" %
      (t.get("prompt_n"), t.get("cache_n"), ttft(d3), t.get("predicted_per_second", 0)))

print("=== 3) SSD session 文件 save/restore ===")
try:
    s = post("/slots/0?action=save", {"filename": "chatA.bin"})
    print("  save:", {k: s.get(k) for k in ("n_saved", "n_written", "timings")})
    r = post("/slots/0?action=restore", {"filename": "chatA.bin"})
    print("  restore:", {k: r.get(k) for k in ("n_restored", "n_read", "timings")})
except Exception as e:
    print("  失败:", str(e)[:200])
