#!/bin/sh
# 容器启动流程：起自动存盘 → 起 app → 等服务就绪 → 自动恢复最新存档 → 守护 app
set -u
/opt/strata/autosave.sh &
python3 -m serve.server --engine strata \
     --config /config/strata-final.json \
     --slot-save-path /sessions --port 8080 &
APP=$!
trap "kill -TERM $APP 2>/dev/null; wait $APP" TERM INT
# 等待服务就绪（最多 6 分钟）
i=0
while [ $i -lt 120 ]; do
  if curl -sf -m 2 http://127.0.0.1:8080/v1/models >/dev/null 2>&1; then break; fi
  i=$((i+1)); sleep 3
done
if [ "${AUTOSAVE_RESTORE:-1}" = "1" ]; then
  LATEST=$(ls -t /sessions/autosave-*.bin 2>/dev/null | head -1)
  if [ -n "$LATEST" ]; then
    echo "[entrypoint] restoring $(basename "$LATEST")"
    curl -s -m 120 -X POST "http://127.0.0.1:8080/slots/0?action=restore" \
      -H "Content-Type: application/json" -d "{\"filename\":\"$(basename "$LATEST")\"}" >/dev/null 2>&1 || true
  fi
fi
wait $APP
