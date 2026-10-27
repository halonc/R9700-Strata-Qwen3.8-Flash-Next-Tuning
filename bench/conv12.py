#!/usr/bin/env python3
"""12 条多轮对话（每轮重发完整历史），验证跨对话缓存是否真的按对话命中。"""
import json, random, string, time, urllib.request

BASE = "http://127.0.0.1:8080"
MID = json.loads(urllib.request.urlopen(BASE + "/v1/models", timeout=10).read())["data"][0]["id"]
W = "系统 推理 缓存 专家 带宽 优化 显存 调度".split()


def post(body, timeout=1200):
    r = urllib.request.Request(BASE + "/v1/chat/completions", data=json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"})
    t0 = time.time()
    d = json.loads(urllib.request.urlopen(r, timeout=timeout).read())
    d["_wall"] = time.time() - t0
    return d


def mk(seed, nwords=3000):
    r = random.Random(seed)
    return "C%d-" % seed + "".join(r.choice(string.ascii_lowercase) for _ in range(6)) + " " + " ".join(r.choice(W) for _ in range(nwords))


def chat(msgs, mt=40):
    return post({"model": MID, "max_tokens": mt, "temperature": 0.2, "messages": msgs})


N = 12
convs = [mk(i) for i in range(N)]
hist = [[] for _ in range(N)]
reply = ["" for _ in range(N)]

print("=== pass 1: open %d conversations (all cold) ===" % N)
cold = []
t0 = time.time()
for i in range(N):
    msgs = [{"role": "user", "content": convs[i] + "\n\n问题一：讲什么？"}]
    d = chat(msgs)
    t = d["timings"]
    reply[i] = d["choices"][0]["message"].get("content") or ""
    hist[i] = msgs + [{"role": "assistant", "content": reply[i]}]
    cold.append((t.get("prompt_n"), t.get("prompt_ms", 0) / 1000))
    print("  #%d prompt_n=%5s TTFT %4.1fs" % (i + 1, t.get("prompt_n"), cold[-1][1]))
print("  %d cold conversations took %.1fs total" % (N, time.time() - t0))

print("=== pass 2: round-robin back, each request resends the full history ===")
warm = []
for i in range(N):
    msgs = hist[i] + [{"role": "user", "content": "问题二：再具体一点？"}]
    d = chat(msgs)
    t = d["timings"]
    warm.append((t.get("prompt_n"), t.get("cache_n"), t.get("prompt_ms", 0) / 1000))
    print("  #%d prompt_n=%5s cached=%5s TTFT %4.2fs" %
          (i + 1, t.get("prompt_n"), t.get("cache_n"), warm[-1][2]))

print("=== summary ===")
hits = sum(1 for w in warm if (w[1] or 0) > 0)
print("  cold TTFT mean %.1fs | hot TTFT mean %.2fs | %d of %d hit the cache" %
      (sum(c[1] for c in cold) / N, sum(w[2] for w in warm) / N, hits, N))
