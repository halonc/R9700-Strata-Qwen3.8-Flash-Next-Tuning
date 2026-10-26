#!/usr/bin/env python3
"""Strata 测速：prefill(TTFT) / decode（服务端 timings）。"""
import json, os, random, string, http.client, statistics, sys, threading, time

HOST, PORT = "127.0.0.1", int(os.environ.get("PORT", 8080))
LABEL = os.environ.get("LABEL", "run")


def req(path, body=None, timeout=1800):
    c = http.client.HTTPConnection(HOST, PORT, timeout=timeout)
    c.request("POST" if body is not None else "GET", path,
              body=json.dumps(body) if body is not None else None,
              headers={"Content-Type": "application/json"})
    return c.getresponse()


def model_id():
    d = json.loads(req("/v1/models").read())
    return d["data"][0]["id"]


WORDS = "系统 推理 缓存 专家 带宽 优化 显存 调度 验证 质量 索引 队列 拓扑".split()


def prompt(n_chars):
    rnd = random.Random()
    nonce = "N" + "".join(rnd.choice(string.ascii_lowercase) for _ in range(12))
    return nonce + " " + " ".join(rnd.choice(WORDS) for _ in range(n_chars // 3 + 1))


def chat(m, p, max_tokens, temp=0.0):
    body = {"model": m, "max_tokens": max_tokens, "temperature": temp,
            "messages": [{"role": "user", "content": p}]}
    t0 = time.time()
    r = req("/v1/chat/completions", body)
    raw = r.read().decode()
    if r.status != 200:
        return {"error": r.status, "body": raw[:300]}
    d = json.loads(raw)
    d["_wall"] = time.time() - t0
    return d


def main():
    m = model_id()
    out = {"label": LABEL, "model": m, "ts": time.strftime("%F %T")}
    print("== %s model=%s" % (LABEL, m))
    pre = {}
    for nchars in (int(x) for x in os.environ.get("SIZES", "6000,22000").split(",")):
        d = chat(m, prompt(nchars), 1)
        if "error" in d:
            print("  prefill ERR", d)
            break
        t = d.get("timings", {})
        pt, pp = t.get("prompt_n"), t.get("prompt_per_second")
        if not pt:
            print("  no timings:", list(d.keys()))
            break
        pre[nchars] = {"prompt_n": pt, "pp": round(pp), "ttft_s": round(t.get("ttft_ms", 0) / 1000, 2)}
        print("  prefill ~%6d ch -> %7d tok  TTFT %6.1fs  %6.0f tok/s" %
              (nchars, pt, t.get("ttft_ms", 0) / 1000, pp))
    out["prefill"] = pre

    dec = []
    for temp, tag in ((0.0, "贪心"), (0.7, "采样")):
        vals = []
        for i in range(2):
            d = chat(m, prompt(700), int(os.environ.get("DECODE_TOK", "300")), temp)
            if "error" in d:
                print("  decode ERR", d)
                break
            t = d.get("timings", {})
            tg = t.get("predicted_per_second")
            acc = (t.get("draft_n_accepted", 0) / t["draft_n"]) if t.get("draft_n") else 0
            vals.append(tg)
            print("  decode %s #%d: %d tok  %6.1f tok/s  %.2f ms/tok  接受 %.0f%%" %
                  (tag, i + 1, t.get("predicted_n", 0), tg, t.get("predicted_per_token_ms", 0), acc * 100))
        if vals:
            dec.append({"temp": temp, "mean": round(statistics.mean(vals), 1)})
    out["decode"] = dec

    if os.environ.get("CONC"):
        conc = int(os.environ["CONC"])
        res = [None] * conc

        def run(i):
            t0 = time.time()
            d = chat(m, prompt(700), 200, 0.0)
            res[i] = (d.get("timings", {}).get("predicted_n", 0), time.time() - t0)

        th = [threading.Thread(target=run, args=(i,)) for i in range(conc)]
        t0 = time.time()
        [x.start() for x in th]
        [x.join() for x in th]
        wall = time.time() - t0
        tot = sum(r[0] for r in res if r)
        print("  conc %d: %d tok / %.1fs -> 聚合 %.1f tok/s" % (conc, tot, wall, tot / wall))
        out["conc"] = {"n": conc, "agg": round(tot / wall, 1)}

    json.dump(out, open("./data/strata-%s.json" % LABEL, "w"), ensure_ascii=False, indent=1)
    print("  saved ./data/strata-%s.json" % LABEL)


main()
