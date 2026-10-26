import json, os, random, string, statistics, sys, urllib.request
M="R9700-Qwen3.8-FlashN-FP8iQ4r"; U="http://127.0.0.1:8080/v1/chat/completions"
words="系统 推理 缓存 专家 带宽 优化 显存 调度 验证 质量".split()
def run(nchars):
    nonce="N-"+"".join(random.choice(string.ascii_lowercase) for _ in range(16))
    p=nonce+" "+" ".join(random.choice(words) for _ in range(nchars//3))
    body=json.dumps({"model":M,"max_tokens":1,"messages":[{"role":"user","content":p}]}).encode()
    r=urllib.request.Request(U,data=body,headers={"Content-Type":"application/json"})
    d=json.loads(urllib.request.urlopen(r,timeout=900).read())
    t=d["timings"]; return t["prompt_n"], t["prompt_per_second"]
tag=sys.argv[1]
out={}
for nchars,label in ((11000,"16K"),(24000,"32K")):
    vals=[]
    for i in range(3):
        n,pp=run(nchars); vals.append(pp)
        print("  %s run%d: %d tok  %.0f tok/s" % (label,i+1,n,pp), flush=True)
    out[label]={"mean":statistics.mean(vals),"min":min(vals),"max":max(vals)}
print("%s summary: %s" % (tag, json.dumps({k:round(v["mean"]) for k,v in out.items()})))
print("%s detail:  %s" % (tag, json.dumps({k:[round(v["min"]),round(v["max"])] for k,v in out.items()})))
