#!/usr/bin/env python3
"""逐项验证：识图 / 并发 batch / 跨对话缓存 / 速度。"""
import base64, json, os, random, string, threading, time, urllib.request

BASE = "http://127.0.0.1:8080"
MID = json.loads(urllib.request.urlopen(BASE + "/v1/models", timeout=10).read())["data"][0]["id"]
WORDS = "系统 推理 缓存 专家 带宽 优化 显存 调度 验证 质量 索引".split()


def post(body, timeout=1800):
    r = urllib.request.Request(BASE + "/v1/chat/completions",
                               data=json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"})
    t0 = time.time()
    d = json.loads(urllib.request.urlopen(r, timeout=timeout).read())
    d["_wall"] = time.time() - t0
    return d


def big_prompt(ntok_chars):
    rnd = random.Random()
    nonce = "N" + "".join(rnd.choice(string.ascii_lowercase) for _ in range(10))
    return nonce + " " + " ".join(rnd.choice(WORDS) for _ in range(ntok_chars // 3))


def ask(prompt, maxtok=200, temp=0.7):
    return post({"model": MID, "max_tokens": maxtok, "temperature": temp,
                 "messages": [{"role": "user", "content": prompt}]})


print("model:", MID)

# 1) 识图
try:
    img = base64.b64encode(open(os.environ.get("TEST_IMAGE", "./vision-test.png"), "rb").read()).decode()
    d = post({"model": MID, "max_tokens": 200, "temperature": 0.2,
              "messages": [{"role": "user", "content": [
                  {"type": "text", "text": "这张图里有哪些颜色？简短回答。"},
                  {"type": "image_url", "image_url": {"url": "data:image/png;base64," + img}}]}]})
    t = d.get("timings", {})
    msg = d["choices"][0]["message"]
    print("[识图] 内容:", (msg.get("content") or "")[:90].replace("\n", " "),
          "| prompt_n:", t.get("prompt_n"), "| %.1fs" % d["_wall"])
except Exception as e:
    print("[识图] 失败:", e)

# 2) 并发（batch）
conc = 4
res = [None] * conc


def one(i):
    t0 = time.time()
    d = ask(big_prompt(2400), 200, 0.7)
    res[i] = (d.get("timings", {}).get("predicted_n", 0), time.time() - t0,
              d.get("timings", {}).get("predicted_per_second", 0))


th = [threading.Thread(target=one, args=(i,)) for i in range(conc)]
t0 = time.time()
[x.start() for x in th]
[x.join() for x in th]
wall = time.time() - t0
tot = sum(r[0] for r in res if r)
print("[并发] %d 路: 每路 %.1f tok/s, 聚合 %.1f tok/s, 墙钟 %.1fs" %
      (conc, sum(r[2] for r in res if r) / conc, tot / wall, wall))

# 3) 跨对话缓存：A(长) -> B(另一段) -> A(同一段追问)
A = big_prompt(60000)          # ~40K tokens
B = big_prompt(6000)
d1 = ask(A + "\n\n问题一：这段在讲什么？", 120)
print("[缓存] 第1轮 A: prompt_n=%s ttft=%.1fs" %
      (d1.get("timings", {}).get("prompt_n"), d1.get("timings", {}).get("prompt_ms", 0) / 1000))
d2 = ask(B + "\n\n问题：这段在讲什么？", 120)
print("[缓存] 第2轮 B: prompt_n=%s ttft=%.1fs" %
      (d2.get("timings", {}).get("prompt_n"), d2.get("timings", {}).get("prompt_ms", 0) / 1000))
d3 = ask(A + "\n\n问题二：再具体一点？", 120)
tt = d3.get("timings", {})
print("[缓存] 第3轮 A 再次: prompt_n=%s cached=%s ttft=%.1fs decode=%.1f tok/s" %
      (tt.get("prompt_n"), tt.get("cache_n"), tt.get("prompt_ms", 0) / 1000, tt.get("predicted_per_second", 0)))
