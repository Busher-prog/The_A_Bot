#!/usr/bin/env bash
# Installs the new The A bot on the VPS in place of the old one (/opt/the-a-bd).
# Run:  sudo bash install.sh
#
# 1. backs up the old bot folder to /root/old-bot-backup-<date>.tar.gz
# 2. installs git + python, creates system user "thea", downloads the code to /opt/the-a-bot
# 3. writes /opt/the-a-bot/.env: token taken from the old bot, manager = the old bot's master
#    (Ksenia), journals continue in the old folder /opt/the-a-bd
# 4. stops the old service the-a-botpoller and starts the new one (the-a-bot)
#
# Rollback: sudo systemctl disable --now the-a-bot && sudo systemctl enable --now the-a-botpoller
set -euo pipefail

REPO="https://github.com/Busher-prog/The_A_Bot.git"
APP=/opt/the-a-bot
SVC=the-a-bot
APP_USER=thea
OLD_DIR=/opt/the-a-bd
OLD_SVC=the-a-botpoller

say()  { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m%s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m%s\033[0m\n' "$*"; exit 1; }

[[ $EUID -eq 0 ]] || die "Запустите так: sudo bash install.sh"

# --- 1. Backup ---------------------------------------------------------------
say "1/4 Резервная копия старого бота"
if [[ -d "$OLD_DIR" ]]; then
  BACKUP="/root/old-bot-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
  tar -czf "$BACKUP" -C "$(dirname "$OLD_DIR")" "$(basename "$OLD_DIR")"
  echo "Сохранено: $BACKUP"
else
  warn "Папки $OLD_DIR нет — журналы будут в $APP/data"
fi

# --- 2. Code -----------------------------------------------------------------
say "2/4 Устанавливаю программы и скачиваю код"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git python3 python3-venv >/dev/null
id "$APP_USER" &>/dev/null || useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
if [[ -d "$APP/.git" ]]; then
  sudo -u "$APP_USER" git -C "$APP" pull -q --ff-only
else
  install -d -o "$APP_USER" -g "$APP_USER" "$APP"
  sudo -u "$APP_USER" git clone -q "$REPO" "$APP"
fi
sudo -u "$APP_USER" python3 -m venv "$APP/.venv"
sudo -u "$APP_USER" "$APP/.venv/bin/pip" install -q --upgrade pip
sudo -u "$APP_USER" "$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt"
echo "Код: $(sudo -u "$APP_USER" git -C "$APP" log -1 --format='%h %s')"

# --- 3. Settings ---------------------------------------------------------------
say "3/4 Настройки"
if [[ -f "$APP/.env" ]]; then
  echo "Файл $APP/.env уже есть — оставляю как есть."
else
  TOKEN=""; MANAGER=""
  if [[ -f "$OLD_DIR/.env" ]]; then
    TOKEN=$(grep -E '^TELEGRAM_INTAKE_BOT_TOKEN=' "$OLD_DIR/.env" | head -1 | cut -d= -f2- | tr -d "\"' ")
  fi
  if [[ -f "$OLD_DIR/master.json" ]]; then
    MANAGER=$(python3 -c "import json;print(json.load(open('$OLD_DIR/master.json')).get('ksenia_chat_id',''))")
  fi
  [[ -n "$TOKEN" ]] || { read -r -s -p "Токен бота из @BotFather (ввод скрыт): " TOKEN </dev/tty; echo; }
  [[ -n "$MANAGER" ]] || read -r -p "Telegram ID менеджера (число из /myid): " MANAGER </dev/tty
  [[ "$MANAGER" =~ ^-?[0-9]+$ ]] || die "ID менеджера должен быть числом"
  DATA_DIR=$([[ -d "$OLD_DIR" ]] && echo "$OLD_DIR" || echo "$APP/data")
  umask 077
  printf 'BOT_TOKEN=%s\nMANAGERS_CHAT_ID=%s\nDATA_DIR=%s\n' "$TOKEN" "$MANAGER" "$DATA_DIR" > "$APP/.env"
  chown "$APP_USER:$APP_USER" "$APP/.env"; chmod 600 "$APP/.env"
  echo "Токен взят из старого бота, заявки получает чат $MANAGER, журналы в $DATA_DIR"
fi
DATA_DIR=$(grep -E '^DATA_DIR=' "$APP/.env" | cut -d= -f2-)
install -d "$DATA_DIR"
chown -R "$APP_USER:$APP_USER" "$DATA_DIR"

# --- 4. Switch -------------------------------------------------------------------
say "4/4 Переключаю: старый бот → новый"
if systemctl list-unit-files "$OLD_SVC.service" --no-legend 2>/dev/null | grep -q "$OLD_SVC"; then
  systemctl disable --now "$OLD_SVC" && echo "Старая служба $OLD_SVC остановлена (файлы не тронуты)"
fi
cp "$APP/deploy/the-a-bot.service" /etc/systemd/system/$SVC.service
systemctl daemon-reload
systemctl enable -q $SVC
systemctl restart $SVC
sleep 8
journalctl -u $SVC --no-pager -n 6 -o cat

if systemctl is-active -q $SVC && journalctl -u $SVC -n 30 --no-pager | grep -q "Run polling"; then
  say "Готово! Новый бот работает. Проверьте /start и QR-коды."
else
  warn "Новый бот не запустился. Возвращаю старого."
  systemctl disable --now $SVC || true
  systemctl enable --now "$OLD_SVC" || true
  die "Старый бот снова работает. Пришлите скриншот экрана выше."
fi
echo "Лог: sudo journalctl -u $SVC -f   Обновление: sudo $APP/deploy/update.sh"
echo "Откат: sudo systemctl disable --now $SVC && sudo systemctl enable --now $OLD_SVC"
