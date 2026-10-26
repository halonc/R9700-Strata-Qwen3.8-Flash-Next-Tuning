#!/usr/bin/env python3
"""radiance 测速：prefill(TTFT)、decode(流式)、并发聚合 + 关键指标快照。"""
import json, os, sys, time, random, string, http.client, threading

HOST, PORT = "127.0.0.1", int(os.environ.get("BPORT", 8080))
LABEL = os.environ.get("LABEL", "run")
MODEL = os.environ.get("BMODEL", "")


def req(path, body=None, timeout=1800):
    c = http.client.HTTPConnection(HOST, PORT, timeout=timeout)
    h = {"Content-Type": "application/json"}
    c.request("POST" if body is not None else "GET", path,
              body=json.dumps(body) if body is not None else None, headers=h)
    return c.getresponse()


def metrics():
    txt = req("/metrics").read().decode()
    out = {}
    for line in txt.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        k, v = line.rsplit(" ", 1)
        k = k.split("{")[0]
        try:
            out[k] = float(v)
        except ValueError:
            pass
    return out


def model_id():
    if MODEL:
        return MODEL
    return json.loads(req("/v1/models").read())["data"][0]["id"]


WORDS = "系统 推理 缓存 专家 带宽 优化 显存 调度 验证 质量 索引 队列 拓扑 采样 延迟 吞吐 模型 解码 预填充".split()


def make_prompt(n_chars):
    rnd = random.Random()
    nonce = "NONCE-" + "".join(rnd.choice(string.ascii_lowercase) for _ in range(24)) + "\n"
    body = " ".join(rnd.choice(WORDS) for _ in range(n_chars // 3 + 1))
    return (nonce + body)[:n_chars]


def chat(model, prompt, max_tokens, stream):
    body = {"model": model, "max_tokens": max_tokens, "temperature": float(os.environ.get("TEMP", "0.0")), "ignore_eos": True,
            "chat_template_kwargs": {"enable_thinking": False},
            "stream": stream,
            "messages": [{"role": "user", "content": prompt}]}
    t0 = time.time()
    r = req("/v1/chat/completions", body)
    if r.status != 200:
        return {"error": r.status, "body": r.read().decode()[:300]}
    if not stream:
        d = json.loads(r.read())
        wall = time.time() - t0
        u = d.get("usage", {})
        return {"wall": wall, "ttft": wall, "prompt_tokens": u.get("prompt_tokens", 0),
                "ctok": u.get("completion_tokens", 0)}
    ttft = None
    first = last = None
    deltas = 0
    ptok = 0
    ctok = 0
    buf = b""
    while True:
        chunk = r.read(4096)
        if not chunk:
            break
        buf += chunk
        while b"\n\n" in buf:
            ev, buf = buf.split(b"\n\n", 1)
            for line in ev.splitlines():
                if not line.startswith(b"data: "):
                    continue
                payload = line[6:].strip()
                if payload == b"[DONE]":
                    continue
                try:
                    d = json.loads(payload)
                except Exception:
                    continue
                u = d.get("usage") or {}
                if u:
                    ptok = u.get("prompt_tokens", ptok)
                    ctok = u.get("completion_tokens", ctok)
                ch = d.get("choices") or [{}]
                delta = ch[0].get("delta") or {}
                if delta.get("content"):
                    now = time.time()
                    if first is None:
                        first = now
                        ttft = now - t0
                    last = now
                    deltas += 1
    wall = time.time() - t0
    ntok = ctok or deltas
    return {"wall": wall, "ttft": ttft, "prompt_tokens": ptok, "ctok": ntok,
            "decode_s": (last - first) if (first and last) else None}


PROSE = "请用中文详细写一段关于分布式系统一致性的说明，尽量展开，不要省略细节。\n\n"


def main():
    m = model_id()
    res = {"label": LABEL, "model": m, "ts": time.strftime("%F %T")}
    print("== %s model=%s" % (LABEL, m))
    pre = {}
    for ntok_t in (int(x) for x in os.environ.get("TOKENS", "4000,16000").split(",")):
        nchars = int(ntok_t * 1.45)
        p = make_prompt(nchars)
        r = chat(m, p, 1, False)
        if "error" in r:
            print("  prefill ERR", r)
            break
        pt = r["prompt_tokens"]
        t = r["ttft"] or 1e-9
        pre[str(ntok_t)] = {"prompt_tokens": pt, "ttft_s": round(t, 2), "prefill_tps": round(pt / t)}
        print("  prefill ~%6d tok -> %7d tok  TTFT %6.2fs  %7.0f tok/s" % (ntok_t, pt, t, pt / t))
    res["prefill"] = pre

    dec = []
    for i in range(int(os.environ.get("DECODE_REPS", "3"))):
        p = PROSE + make_prompt(80)
        r = chat(m, p, int(os.environ.get("DECODE_TOK", "256")), True)
        if "error" in r:
            print("  decode ERR", r)
            break
        ds = r["decode_s"] or 1e-9
        rate = (r["ctok"] - 1) / ds if r["ctok"] else 0
        dec.append(round(rate, 1))
        if i == 0:
            continue
        print("  decode #%d: %d tok in %.2fs -> %.1f tok/s (TTFT %.2fs)" %
              (i + 1, r["ctok"], ds, rate, r["ttft"] or -1))
    res["decode_tps"] = dec

    for conc in (2, 4):
        outs = [None] * conc

        def run(i):
            p = PROSE + make_prompt(80)
            t0 = time.time()
            r = chat(m, p, 128, True)
            outs[i] = (r.get("ctok", 0), time.time() - t0, r.get("decode_s"))

        th = [threading.Thread(target=run, args=(i,)) for i in range(conc)]
        t0 = time.time()
        [t.start() for t in th]
        [t.join() for t in th]
        wall = time.time() - t0
        tot = sum(o[0] for o in outs if o)
        agg = tot / wall if wall else 0
        durs = [o[2] or o[1] for o in outs if o]
        ratio = min(durs) / max(durs) if durs else 0
        print("  conc %d: %d tok / %.2fs -> agg %.1f tok/s, dur ratio %.2f" % (conc, tot, wall, agg, ratio))
        res["conc%d" % conc] = {"agg_tps": round(agg, 1), "dur_ratio": round(ratio, 2), "tokens": tot}

    m1 = metrics()
    keys = ["radiance:draft_acceptance_ratio", "radiance:decode_tokens_per_second",
            "radiance:prefill_tokens_per_second", "radiance:linear_prefix_cache_hit_rate",
            "vllm:gpu_prefix_cache_hit_rate", "radiance:decode_step_seconds_recent",
            "radiance:engine_steps_decode_total", "radiance:prefix_cache_evictions_total",
            "radiance:num_requests_preempted", "radiance:http_queue_depth"]
    snap = {}
    for k in keys:
        snap[k] = m1.get(k)
    res["metrics"] = snap
    print("  metrics:", json.dumps({k.split(":")[1]: v for k, v in snap.items()}))
    out = "./data/%s.json" % LABEL
    json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
    print("  saved", out)


main()
