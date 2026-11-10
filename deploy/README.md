# Установка на VPS (Ubuntu / Debian)

## Быстрый способ: один скрипт

Подключитесь к серверу (`ssh root@IP`), создайте файл и вставьте в него содержимое
[`deploy/install.sh`](install.sh) (на GitHub: открыть файл → кнопка **Raw** → выделить всё → копировать):

```bash
nano install.sh      # вставить, затем Ctrl+O, Enter, Ctrl+X
bash install.sh
```

Скрипт сам найдёт и остановит старого бота (спросит), сделает копию его папки,
установит нового и запустит как службу. Ниже — те же шаги вручную.

---

Все команды выполняются на сервере по SSH.

## 0. Остановить старого бота

С одним токеном может работать только одна программа. Найдите старую:

```bash
ps aux | grep -i -E "python|node|bot" | grep -v grep
systemctl list-units --type=service | grep -i bot
pm2 list 2>/dev/null; docker ps 2>/dev/null; crontab -l 2>/dev/null
```

Сохраните копию её папки на всякий случай, затем остановите и отключите автозапуск
(`systemctl stop <name> && systemctl disable <name>`, `pm2 delete <name>`, `docker stop <id>` и т. п.).

## 1. Подготовка

```bash
sudo apt update && sudo apt install -y git python3 python3-venv
python3 --version   # нужна 3.10 или новее
sudo useradd --system --create-home --shell /usr/sbin/nologin thea
```

## 2. Доступ сервера к приватному репозиторию (deploy key)

```bash
sudo -u thea ssh-keygen -t ed25519 -N "" -f /home/thea/.ssh/id_ed25519
sudo cat /home/thea/.ssh/id_ed25519.pub
```

Скопируйте выведенную строку: GitHub → репозиторий → Settings → Deploy keys → Add deploy key
(галочку «Allow write access» не ставить).

## 3. Скачать код и установить

```bash
sudo mkdir -p /opt/the-a-bot && sudo chown thea:thea /opt/the-a-bot
sudo -u thea git clone git@github.com:Busher-prog/The_A_Bot.git /opt/the-a-bot
cd /opt/the-a-bot
sudo -u thea python3 -m venv .venv
sudo -u thea .venv/bin/pip install -r requirements.txt
```

## 4. Настройки

```bash
sudo -u thea cp .env.example .env
sudo -u thea nano .env      # BOT_TOKEN и MANAGERS_CHAT_ID
sudo chmod 600 .env
```

## 5. Запуск

```bash
sudo cp deploy/the-a-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now the-a-bot
sudo systemctl status the-a-bot
```

Лог: `sudo journalctl -u the-a-bot -f`

## Обновление после изменений на GitHub

```bash
sudo /opt/the-a-bot/deploy/update.sh
```

## Сменить получателя заявок или токен

Отредактируйте `/opt/the-a-bot/.env` и выполните `sudo systemctl restart the-a-bot`.
