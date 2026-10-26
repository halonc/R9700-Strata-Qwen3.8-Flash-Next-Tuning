#!/bin/sh
# 每 INTERVAL 秒把 slot0 的对话状态存到 /sessions/autosave-N.bin（轮转 KEEP 份）
# 失败静默（引擎尚未就绪、无对话、正在 prefill 等都不影响服务）
INTERVAL=${AUTOSAVE_INTERVAL:-900}
KEEP=${AUTOSAVE_KEEP:-4}
SAVE_DIR=${AUTOSAVE_DIR:-/sessions}
i=0
sleep 120
while true; do
  name="autosave-$((i % KEEP)).bin"
  curl -s -m 30 -X POST "http://127.0.0.1:8080/slots/0?action=save" \
       -H "Content-Type: application/json" -d "{\"filename\":\"$name\"}" >/dev/null 2>&1 || true
  i=$((i+1))
  sleep "$INTERVAL"
done
