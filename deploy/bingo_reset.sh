#!/usr/bin/env bash
# Clears ONLY the business bingo (participants, answers, gifts) — e.g. after a test run.
# Leads, client messages, calculator etc. are not touched. A backup is kept.
# Run on the server: sudo /opt/the-a-bot/deploy/bingo_reset.sh
set -euo pipefail

APP=/opt/the-a-bot
DATA_DIR=$(grep -E '^DATA_DIR=' "$APP/.env" | cut -d= -f2-)
DATA_DIR=${DATA_DIR:-$APP/data}
STAMP=$(date +%Y%m%d-%H%M%S)

[[ $EUID -eq 0 ]] || { echo "Запустите так: sudo $0"; exit 1; }
[[ -f "$DATA_DIR/state.json" ]] || { echo "Нет $DATA_DIR/state.json — сбрасывать нечего."; exit 0; }

systemctl stop the-a-bot   # the bot keeps the data in memory: stop it first
cp "$DATA_DIR/state.json" "$DATA_DIR/state.before-bingo-reset-$STAMP.json"
[[ -f "$DATA_DIR/bingo.jsonl" ]] && mv "$DATA_DIR/bingo.jsonl" "$DATA_DIR/bingo.test-$STAMP.jsonl"

python3 - "$DATA_DIR/state.json" <<'EOF'
import json, sys
path = sys.argv[1]
state = json.load(open(path, encoding="utf-8"))
players = len(state.get("bingo") or {})
for key in [k for k in state if k == "bingo" or k.startswith("bingo_")]:
    del state[key]
json.dump(state, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"Бинго очищено: удалено участников - {players}")
EOF

chown -R thea:thea "$DATA_DIR"
systemctl start the-a-bot
sleep 3
systemctl is-active -q the-a-bot && echo "Готово, бот работает. Копия: state.before-bingo-reset-$STAMP.json"
