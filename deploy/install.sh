#!/usr/bin/env bash
# One-time installation of The A bot on a VPS (Ubuntu / Debian).
# Run as root:  bash install.sh
#
# What it does:
#   1. shows programs that look like the old bot, backs up its folder and stops it (asks first)
#   2. installs git + python, creates system user "thea"
#   3. creates a read-only GitHub deploy key and waits until you add it to the repo
#   4. downloads the code to /opt/the-a-bot and installs dependencies
#   5. asks for the bot token and the manager's Telegram ID, writes /opt/the-a-bot/.env
#   6. installs the systemd service: the bot starts now, after crashes and after reboots
set -euo pipefail

REPO="git@github.com:Busher-prog/The_A_Bot.git"
APP=/opt/the-a-bot
SVC=the-a-bot
APP_USER=thea

say()  { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m%s\033[0m\n' "$*"; }
ask()  { local a; read -r -p "$1 " a </dev/tty; printf '%s' "$a"; }

[[ $EUID -eq 0 ]] || { echo "Запустите от root: sudo bash install.sh"; exit 1; }

# --- 1. Old bot -------------------------------------------------------------
say "1/6 Ищу старого бота"
echo "--- процессы:"
ps -eo pid,user,etime,args | grep -i -E "python|node|bot" | grep -v -E "grep|install.sh|unattended|networkd-dispatcher" || echo "(ничего)"
echo "--- службы systemd:"
systemctl list-units --type=service --state=running --no-legend 2>/dev/null \
  | grep -i -E "bot|python|node|telegram" || echo "(ничего)"
command -v pm2    >/dev/null && { echo "--- pm2:";    pm2 list || true; }
command -v docker >/dev/null && { echo "--- docker:"; docker ps || true; }
echo "--- cron:"; crontab -l 2>/dev/null || echo "(нет)"

OLD_DIR=$(ask "Папка старого бота для резервной копии (Enter — пропустить):")
if [[ -n "$OLD_DIR" && -d "$OLD_DIR" ]]; then
  BACKUP="/root/old-bot-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
  tar -czf "$BACKUP" -C "$(dirname "$OLD_DIR")" "$(basename "$OLD_DIR")"
  echo "Копия сохранена: $BACKUP"
fi

OLD_SVC=$(ask "Имя службы systemd старого бота, чтобы остановить (Enter — пропустить):")
if [[ -n "$OLD_SVC" ]]; then
  systemctl stop "$OLD_SVC" && systemctl disable "$OLD_SVC" && echo "Служба $OLD_SVC остановлена"
fi
OLD_PID=$(ask "PID процесса старого бота, чтобы остановить (Enter — пропустить):")
if [[ -n "$OLD_PID" ]]; then
  kill "$OLD_PID" && echo "Процесс $OLD_PID остановлен"
  warn "Если старый бот запускался через pm2/docker/cron, он может подняться снова — сообщите об этом."
fi

# --- 2. System packages -----------------------------------------------------
say "2/6 Устанавливаю git и Python"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git python3 python3-venv openssh-client >/dev/null
python3 -c 'import sys; assert sys.version_info >= (3, 10), sys.version' \
  || { echo "Нужен Python 3.10+, на сервере: $(python3 --version)"; exit 1; }
id "$APP_USER" &>/dev/null || useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"

# --- 3. Deploy key ----------------------------------------------------------
say "3/6 Ключ доступа к GitHub"
HOME_DIR=$(getent passwd "$APP_USER" | cut -d: -f6)
install -d -m 700 -o "$APP_USER" -g "$APP_USER" "$HOME_DIR/.ssh"
[[ -f "$HOME_DIR/.ssh/id_ed25519" ]] || sudo -u "$APP_USER" ssh-keygen -q -t ed25519 -N "" -C "the-a-bot-server" -f "$HOME_DIR/.ssh/id_ed25519"
ssh-keyscan -t ed25519 github.com 2>/dev/null | sudo -u "$APP_USER" tee "$HOME_DIR/.ssh/known_hosts" >/dev/null

until sudo -u "$APP_USER" git ls-remote "$REPO" &>/dev/null; do
  echo
  echo "Добавьте этот ключ на GitHub:"
  echo "  github.com/Busher-prog/The_A_Bot → Settings → Deploy keys → Add deploy key"
  echo "  Title: server, Key: строка ниже, галочку «Allow write access» НЕ ставить"
  echo
  cat "$HOME_DIR/.ssh/id_ed25519.pub"
  echo
  ask "Когда добавите — нажмите Enter" >/dev/null
done
echo "Доступ к репозиторию есть."

# --- 4. Code ----------------------------------------------------------------
say "4/6 Скачиваю код"
if [[ -d "$APP/.git" ]]; then
  sudo -u "$APP_USER" git -C "$APP" pull --ff-only
else
  install -d -o "$APP_USER" -g "$APP_USER" "$APP"
  sudo -u "$APP_USER" git clone -q "$REPO" "$APP"
fi
sudo -u "$APP_USER" python3 -m venv "$APP/.venv"
sudo -u "$APP_USER" "$APP/.venv/bin/pip" install -q --upgrade pip
sudo -u "$APP_USER" "$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt"

# --- 5. Settings ------------------------------------------------------------
say "5/6 Настройки"
if [[ -f "$APP/.env" ]] && [[ "$(ask 'Файл .env уже есть. Оставить как есть? [Y/n]')" != [nN]* ]]; then
  echo "Оставляю $APP/.env"
else
  read -r -s -p "Токен НАСТОЯЩЕГО бота из @BotFather (ввод скрыт): " TOKEN </dev/tty; echo
  MANAGER=$(ask "Telegram ID менеджера (число из /myid):")
  [[ "$MANAGER" =~ ^-?[0-9]+$ ]] || { echo "ID должен быть числом"; exit 1; }
  umask 077
  printf 'BOT_TOKEN=%s\nMANAGERS_CHAT_ID=%s\n' "$TOKEN" "$MANAGER" > "$APP/.env"
  chown "$APP_USER:$APP_USER" "$APP/.env"; chmod 600 "$APP/.env"
fi

# --- 6. Service -------------------------------------------------------------
say "6/6 Запускаю бота"
cp "$APP/deploy/the-a-bot.service" /etc/systemd/system/$SVC.service
systemctl daemon-reload
systemctl enable --now $SVC
systemctl restart $SVC
sleep 6
systemctl --no-pager --lines=0 status $SVC | head -3
journalctl -u $SVC --no-pager -n 8

if journalctl -u $SVC -n 20 --no-pager | grep -q "Run polling"; then
  say "Готово! Бот работает. Проверьте: напишите ему /start или отсканируйте QR."
else
  warn "Бот не запустился — пришлите вывод выше."
fi
echo "Лог: journalctl -u $SVC -f    Обновление: sudo $APP/deploy/update.sh"
