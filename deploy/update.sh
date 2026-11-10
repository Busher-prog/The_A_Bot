#!/usr/bin/env bash
# Pull the latest code from GitHub and restart the bot. Run on the server: sudo /opt/the-a-bot/deploy/update.sh
set -euo pipefail
cd /opt/the-a-bot
sudo -u thea git pull --ff-only
sudo -u thea .venv/bin/pip install -q -r requirements.txt
systemctl restart the-a-bot
sleep 3
systemctl --no-pager --lines=5 status the-a-bot
