# The A — Telegram-бот

Бот [@BusinessManagerTheA_bot](https://t.me/BusinessManagerTheA_bot): стартовые экраны для QR-кодов,
темы, фотоальбом, запись на консультацию, налоговый калькулятор, анкеты и передача всех лидов менеджеру.

## Что умеет

| | |
|---|---|
| **Стартовые экраны** | `/start` — общий экран. QR-коды: `?start=ybc_lisbon`, `iam_lisbon`, `relocate`, `hayat_webinar_13jun`. Источник клиента запоминается и показывается менеджеру |
| **Темы** | Под каждой темой «Написати менеджеру» / «Назад». Выбор темы → карточка менеджеру |
| **Фото** | Текст + кнопка на альбом (`photos` в `texts.yaml`) |
| **Анкеты** | Консультация (имя → контакт → вопрос) и Hayat (4 вопроса, промокод) |
| **Калькулятор** | `/calculator` — 4 вопроса, сравнение 3 структур; результат и менеджеру |
| **Команды** | `/services`, `/jurisdictions`, `/contact`, `/help` |
| **Сообщения клиентов** | Автоответ (рабочее / нерабочее время) + карточка менеджеру с `chat_id` и кнопкой «Написати напряму» |
| **Ответ клиенту** | Менеджер нажимает **Reply** на карточке → бот доставляет ответ (текст, фото, файл) |
| **Согласование постов** | Кнопки ✅/✏️/❌ на постах из `pending_posts.jsonl`: публикация в Telegram-канал, правки, напоминания о правках > 30 мин |
| **Журналы** | `inbox.jsonl`, `sent.jsonl`, `*_leads.jsonl`, `calculator_completions.jsonl`, `state.json` — в `DATA_DIR` (на сервере `/opt/the-a-bd`, те же файлы, что вёл старый бот) |

Кнопки в старых сообщениях (у людей, открывших бота раньше) продолжают работать:
формат кнопок совпадает со старым ботом, а бывшая кнопка «Розіграш» открывает фото.

## Как поменять тексты

Всё в [`content/texts.yaml`](content/texts.yaml): экраны, темы, кнопки, анкеты, автоответы, команды,
описание профиля. Отредактируйте (можно прямо на GitHub) и обновите бота на сервере:
`sudo /opt/the-a-bot/deploy/update.sh`.

- **Новый QR-код:** добавьте экран в `screens` со своим `start_param` →
  ссылка `t.me/BusinessManagerTheA_bot?start=<start_param>`.
- **Новая тема:** добавьте её в нужную группу в `groups` и кнопку `seg_<id>` на экран.

Калькулятор (расчёты и его тексты) — в [`bot/calculator.py`](bot/calculator.py).

## Настройки (`.env`)

| Переменная | Что это |
|---|---|
| `BOT_TOKEN` | Токен из @BotFather |
| `MANAGERS_CHAT_ID` | Кому идут лиды (сейчас — Ксения). Узнать номер: написать боту `/myid` |
| `DATA_DIR` | Папка журналов |

## Рассылка (только вручную)

Сообщение с фото всем, кто пришёл по QR-коду. Без флага ничего не отправляет, только считает:

```bash
cd /opt/the-a-bot && sudo -u thea .venv/bin/python -m bot.broadcast ybc_lisbon            # сколько людей
cd /opt/the-a-bot && sudo -u thea .venv/bin/python -m bot.broadcast ybc_lisbon --preview  # превью менеджеру
cd /opt/the-a-bot && sudo -u thea .venv/bin/python -m bot.broadcast ybc_lisbon --send     # всем
```

## Сервер

Установка и обновление: [deploy/README.md](deploy/README.md).

## Разработка

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # и заполнить; для экспериментов — отдельный тестовый бот
python -m bot
pytest
```

```
content/texts.yaml        все тексты
bot/__main__.py           запуск
bot/handlers/menu.py      /start, QR-экраны, темы, фото, команды
bot/handlers/forms.py     анкеты (консультация, Hayat)
bot/handlers/calculator.py + bot/calculator.py   калькулятор
bot/handlers/manager.py   сообщения клиентов ↔ менеджер
bot/handlers/posts.py     согласование постов
bot/storage.py            журналы и список клиентов
bot/broadcast.py          рассылка
```
