# Сервер (Ubuntu, SkyGroup VPS)

## Первая установка вместо старого бота

В noVNC Console (вход под своим пользователем) одной строкой:

```bash
curl -sL https://raw.githubusercontent.com/Busher-prog/The_A_Bot/main/deploy/install.sh -o i.sh && sudo bash i.sh
```

Скрипт без вопросов:
1. делает архив старого бота `/opt/the-a-bd` в `/root/old-bot-backup-<дата>.tar.gz`;
2. скачивает код в `/opt/the-a-bot`, ставит зависимости;
3. берёт токен из настроек старого бота, получателем лидов ставит его «мастера» (Ксению),
   журналы продолжает писать в `/opt/the-a-bd`;
4. останавливает старую службу `the-a-botpoller` и запускает новую `the-a-bot`.
   Если новая не запустилась — автоматически возвращает старую.

## Повседневное

```bash
sudo /opt/the-a-bot/deploy/update.sh        # подтянуть изменения с GitHub и перезапустить
sudo journalctl -u the-a-bot -f             # лог
sudo nano /opt/the-a-bot/.env               # токен / менеджер, затем: sudo systemctl restart the-a-bot
```

## Приоритет в розыгрыше кепок/футболок бинго

Имена хранятся только на сервере, в `/opt/the-a-bot/.env` (строка `BINGO_VIP=`, имена через `;`,
можно латиницей). Сброс бинго их не трогает. После изменения: `sudo systemctl restart the-a-bot`.

## Сбросить бизнес-бинго (например, после тестового прогона)

Удаляет только участников, ответы и подарки бинго. Лиды и переписка остаются, копия сохраняется.

```bash
sudo /opt/the-a-bot/deploy/bingo_reset.sh
```

## Откат на старого бота

```bash
sudo systemctl disable --now the-a-bot && sudo systemctl enable --now the-a-botpoller
```
