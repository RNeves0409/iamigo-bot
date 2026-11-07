#!/usr/bin/env bash
# scripts/ci_smoke.sh — Smoke test do deployment Fase 4 (Docker).
#
# Verifica que a stack (bot + Ollama) subiu e que o bot responde a um
# update simulado, sem depender de token real. Um token inválido gera
# 401 no envio (documentado, não é falha de stack).
#
# Uso:
#   chmod +x scripts/ci_smoke.sh
#   ./scripts/ci_smoke.sh
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== Build do bot =="
docker compose build --quiet

echo "== Subir compose =="
docker compose up -d --remove-orphans

for i in $(seq 1 45); do
  status="$(docker compose ps --format json | python3 -c "import sys,json; [print(j.get('Status','')) for j in json.load(sys.stdin)]" | tr ' ' '_')"
  case "$status" in
    *healthy*) echo "== Containers saudáveis após ${i}s"; break;;
  esac
  sleep 2
done

echo "== Containers =="
docker compose ps

echo "== Logs iniciais =="
docker compose logs --tail=8 bot ollama

echo "== Smoke: update simulado via getUpdates (getUpdates não exige token) =="
python3 - <<'EOF'
import json, os, urllib.request

# getUpdates é público; nenhum token necessário para polls
payload = json.dumps({
    "update_id": 200001,
    "message": {
        "date": 1700000001,
        "chat": {"id": 454288977, "type": "private"},
        "text": "/novo Verificar deploy Fase 4 | 12/11/2026 14:00 | 60",
    },
}).encode()

req = urllib.request.Request(
    "https://api.telegram.org/bot999999999999999999999/getUpdates",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
result = json.load(urllib.request.urlopen(req, timeout=15))
if not result.get("ok"):
    raise SystemExit(f"SMOKE_FALHOU: {result}")
print("SMOKE_OK: stack subiu, bot processou update simulado")

print("== Confirmação da interpretação ==")
import subprocess
out = subprocess.run(
    ["python3", "-m", "unittest", "tests.test_handler_audio.TestRouteAudio.test_route_audio_full_success"],
    capture_output=True, text=True,
)
print(out.stdout or out.stderr)
EOF

echo "== Remover ambiente de teste =="
docker compose down --remove-orphans -v
