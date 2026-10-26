#!/usr/bin/env python3
"""spec-min-p A/B：3 段不同输入（不同 nonce/内容类型），每段 1K 输出，温度固定 0.7。"""
import json, os, random, string, time, urllib.request

BASE = "http://127.0.0.1:8080"
LABEL = os.environ.get("LABEL", "run")
MID = json.loads(urllib.request.urlopen(BASE + "/v1/models", timeout=10).read())["data"][0]["id"]

# 三类工程内容，避免缓存互相污染（每段独立 nonce 且内容不同）
KINDS = {
    "code": ("下面是一段需求背景，请写出完整的 Python 实现并给出测试。",
             "写一个带重试与超时的异步 HTTP 客户端，要求指数退避、可取消、记录指标。"),
    "config": ("下面是现场信息，请给出排查步骤和修复命令。",
               "某台 Linux 服务器上，两块网卡做 active-backup bonding，升级内核后其中一个 slave 一直 down，"
               "bond 报告 MII Status down，交换机侧看不到光。请按顺序给出诊断命令与修复方案。"),
    "prose": ("请根据下面的材料写一段技术说明。",
              "解释为什么在单卡 32GB 显存上跑 176B MoE 时，把专家权重放主机内存会让 decode 受 PCIe 带宽限制，"
              "而从 CPU 侧计算专家反而可能更快，并结合 batch 与 KV 缓存说明取舍。"),
}
W = "系统 推理 缓存 专家 带宽 优化 显存 调度 验证 质量 索引".split()


def mk_filler(ntok, seed):
    r = random.Random(seed)
    n = "S" + "".join(r.choice(string.ascii_lowercase) for _ in range(10))
    return n + " " + " ".join(r.choice(W) for _ in range(int(ntok / 2.07)))


print("== %s  model=%s" % (LABEL, MID))
results = {}
for i, (kind, (intro, question)) in enumerate(KINDS.items()):
    filler = mk_filler(8000, seed=100 + i)
    prompt = intro + "\n\n" + filler + "\n\n" + question
    body = {"model": MID, "max_tokens": 1024, "temperature": 0.7,
            "messages": [{"role": "user", "content": prompt}]}
    r = urllib.request.Request(BASE + "/v1/chat/completions", data=json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"})
    t0 = time.time()
    d = json.loads(urllib.request.urlopen(r, timeout=1800).read())
    t = d["timings"]
    acc = (t.get("draft_n_accepted", 0) / t["draft_n"] * 100) if t.get("draft_n") else 0
    results[kind] = {"decode": round(t.get("predicted_per_second", 0), 1),
                     "acc": round(acc), "out": t.get("predicted_n"), "wall": round(time.time() - t0, 1)}
    print("  %-7s out=%4d  decode %6.1f tok/s  接受 %3d%%  wall %5.1fs" %
          (kind, t.get("predicted_n"), t.get("predicted_per_second", 0), acc, time.time() - t0))

ds = [v["decode"] for v in results.values()]
accs = [v["acc"] for v in results.values()]
print("  ── 均值: decode %.1f tok/s, 接受 %.0f%%" % (sum(ds) / len(ds), sum(accs) / len(accs)))
json.dump({"label": LABEL, "results": results}, open("./data/ab-spec-%s.json" % LABEL, "w"), indent=1)
