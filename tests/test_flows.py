import json

from aiogram.types import Contact

from tests.conftest import CLIENT, MANAGER, bot_message, labels, msg, press


def journal(storage, name):
    path = storage.dir / name
    return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []


# --- start screens ------------------------------------------------------------------

async def test_plain_start(env, content):
    dp, bot, session, storage = env
    await dp.feed_update(bot, msg("/start"))
    m = session.to(CLIENT.id)[-1]
    assert m.text == content.screens["direct"].text
    assert content.buttons.photos not in labels(m) and content.buttons.consult not in labels(m)
    assert session.to(MANAGER.id) == []  # plain /start is not a lead card (as before)


async def test_ybc_qr_shows_event_screen_and_notifies_ksenia(env, content):
    dp, bot, session, storage = env
    await dp.feed_update(bot, msg("/start ybc_lisbon"))
    m = session.to(CLIENT.id)[-1]
    assert m.text == content.screens["ybc"].text
    assert labels(m)[0] == content.buttons.photos
    card = session.to(MANAGER.id)[-1]
    assert "Новый лид" in card.text and "YBC Lisbon" in card.text and "chat_id: 777" in card.text
    assert card.reply_markup.inline_keyboard[0][0].url == "https://t.me/olena"
    assert storage.user(CLIENT.id)["source"] == "ybc_lisbon"
    assert journal(storage, "inbox.jsonl")[-1]["event"] == "deeplink_start"


async def test_photos_and_consult_only_on_ybc(env, content):
    dp, bot, session, storage = env
    for param, key in (("iam_lisbon", "iam"), ("relocate", "relocate"),
                       ("hayat_webinar_13jun", "hayat")):
        await dp.feed_update(bot, msg(f"/start {param}"))
        m = session.to(CLIENT.id)[-1]
        assert m.text == content.screens[key].text
        assert content.buttons.photos not in labels(m) and content.buttons.consult not in labels(m)


async def test_photos_button(env, content):
    dp, bot, session, storage = env
    await dp.feed_update(bot, press("src:ybc:photos"))
    m = session.to(CLIENT.id)[-1]
    assert m.text == content.photos.text
    assert m.reply_markup.inline_keyboard[0][0].url == str(content.photos.album_url)


async def test_old_raffle_button_in_old_messages_opens_photos(env, content):
    dp, bot, session, storage = env
    await dp.feed_update(bot, press("src:ybc:seg_collection"))
    assert session.to(CLIENT.id)[-1].text == content.photos.text


async def test_topic_then_back(env, content):
    dp, bot, session, storage = env
    await dp.feed_update(bot, press("src:ybc:seg_banks"))
    m = session.to(CLIENT.id)[-1]
    assert m.text == content.groups["common"].topics["banks"].text
    assert "выбрал тему: Банки і рахунки" in session.to(MANAGER.id)[-1].text
    await dp.feed_update(bot, press(m.reply_markup.inline_keyboard[-1][0].callback_data))
    assert session.to(CLIENT.id)[-1].text == content.screens["ybc"].text


async def test_relocate_and_hayat_topics(env, content):
    dp, bot, session, storage = env
    await dp.feed_update(bot, press("src:relocate:seg_spain"))
    assert session.to(CLIENT.id)[-1].text == content.groups["relocate"].topics["spain"].text
    await dp.feed_update(bot, press("src:hayat:seg_it"))
    assert session.to(CLIENT.id)[-1].text == content.groups["hayat"].topics["it"].text


# --- client messages and Ksenia's replies ------------------------------------------------

async def test_free_text_gets_ack_and_card(env, content):
    dp, bot, session, storage = env
    await dp.feed_update(bot, press("src:ybc:seg_taxes"))
    await dp.feed_update(bot, msg("Живу в Португалії, дохід з США"))
    assert session.to(CLIENT.id)[-1].text in (content.replies.ack_work, content.replies.ack_off)
    card = session.to(MANAGER.id)[-1]
    assert "Входящее в боте The A" in card.text and "Живу в Португалії" in card.text
    assert "Тема: Податки і резидентство" in card.text and "chat_id: 777" in card.text
    assert journal(storage, "inbox.jsonl")[-1]["text"] == "Живу в Португалії, дохід з США"


async def test_ksenia_reply_reaches_client_also_for_old_cards(env):
    dp, bot, session, storage = env
    old_card = bot_message("🔔 Входящее в боте The A\n\nИмя: Olena\nuser_id: 777\nchat_id: 777\n")
    await dp.feed_update(bot, msg("Добрий день!", user=MANAGER, reply_to=old_card))
    assert [c.chat_id for c in session.sent("CopyMessage")] == [CLIENT.id]
    assert "Отправлено клиенту" in session.to(MANAGER.id)[-1].text
    assert journal(storage, "sent.jsonl")[-1]["via"] == "master_reply"


async def test_ksenia_plain_message_is_not_a_client_message(env):
    dp, bot, session, storage = env
    await dp.feed_update(bot, msg("hello", user=MANAGER))
    assert "Reply" in session.to(MANAGER.id)[-1].text
    assert session.sent("CopyMessage") == []


async def test_old_command_shows_menu_of_own_source(env, content):
    dp, bot, session, storage = env
    await dp.feed_update(bot, msg("/start iam_lisbon"))
    await dp.feed_update(bot, msg("/setmaster x"))
    assert session.to(CLIENT.id)[-1].text == content.screens["iam"].text


async def test_info_commands(env, content):
    dp, bot, session, storage = env
    for cmd in ("services", "jurisdictions", "contact", "help"):
        await dp.feed_update(bot, msg(f"/{cmd}"))
        assert session.to(CLIENT.id)[-1].text == content.commands_text[cmd]


# --- questionnaires -------------------------------------------------------------------

async def test_consultation(env, content):
    dp, bot, session, storage = env
    await dp.feed_update(bot, press("src:ybc:consult"))
    await dp.feed_update(bot, msg("Олена"))
    await dp.feed_update(bot, msg(contact=Contact(phone_number="+351900000000", first_name="O")))
    await dp.feed_update(bot, msg("Резидентство"))
    card = session.to(MANAGER.id)[-1]
    for part in ("Заявка на консультацію", "Олена", "+351900000000", "Резидентство", "chat_id: 777"):
        assert part in card.text
    assert session.to(CLIENT.id)[-1].text == content.forms["consult"].done
    assert journal(storage, "consultation_leads.jsonl")[-1]["contact"] == "+351900000000"


async def test_consultation_cancel(env, content):
    dp, bot, session, storage = env
    await dp.feed_update(bot, press("src:direct:consult"))
    await dp.feed_update(bot, msg(content.buttons.cancel))
    await dp.feed_update(bot, msg("просто питання"))
    assert "Входящее" in session.to(MANAGER.id)[-1].text  # back to normal mode


async def test_hayat_form_from_old_button(env, content):
    dp, bot, session, storage = env
    await dp.feed_update(bot, press("src:hayat:lead_start"))  # button in old messages
    for answer in ("Ivan", "@ivan", "сейчас", "нет"):
        await dp.feed_update(bot, msg(answer))
    card = session.to(MANAGER.id)[-1]
    assert "Hayat" in card.text and "@ivan" in card.text and "HAYAT15" in card.text
    lead = journal(storage, "hayat_leads.jsonl")[-1]
    assert lead["name"] == "Ivan" and lead["urgency"] == "сейчас"


# --- calculator -------------------------------------------------------------------------

async def test_calculator_full_run(env):
    dp, bot, session, storage = env
    await dp.feed_update(bot, msg("/calculator"))
    for data in ("calc:residence:es", "calc:gross:", "calc:source:", "calc:family:"):
        last = session.to(CLIENT.id)[-1]
        if data.endswith(":"):  # take the first option offered on screen
            data = last.reply_markup.inline_keyboard[0][0].callback_data
        await dp.feed_update(bot, press(data))
    assert "Tax Calculator завершён" in session.to(MANAGER.id)[-1].text
    assert "chat_id: 777" in session.to(MANAGER.id)[-1].text
    assert journal(storage, "calculator_completions.jsonl")[-1]["answers"]["residence"] == "es"


# --- post approval ---------------------------------------------------------------------

def add_post(storage, **fields):
    with (storage.dir / "pending_posts.jsonl").open("a") as f:
        f.write(json.dumps({"id": "p1", "status": "pending", "text": "Post", **fields}) + "\n")


async def test_post_approve_publishes_to_channel(env):
    dp, bot, session, storage = env
    add_post(storage, channel="@TheA_CapitalHouse")
    await dp.feed_update(bot, press("approve:p1", user=MANAGER))
    assert any(m.chat_id == "@TheA_CapitalHouse" and m.text == "Post" for m in session.sent())
    assert journal(storage, "pending_posts.jsonl")[-1]["status"] == "approved"


async def test_post_manual_channel_edit_reject(env):
    dp, bot, session, storage = env
    add_post(storage, channel="Instagram")
    await dp.feed_update(bot, press("approve:p1", user=MANAGER))
    assert journal(storage, "pending_posts.jsonl")[-1]["status"] == "approved_manual"

    await dp.feed_update(bot, press("edit:p1", user=MANAGER))
    await dp.feed_update(bot, msg("коротше", user=MANAGER))
    last = journal(storage, "pending_posts.jsonl")[-1]
    assert last["status"] == "edit_requested" and last["edit_feedback"] == "коротше"


async def test_post_buttons_only_for_manager(env):
    dp, bot, session, storage = env
    add_post(storage, channel="@TheA_CapitalHouse")
    await dp.feed_update(bot, press("approve:p1"))
    assert journal(storage, "pending_posts.jsonl")[-1]["status"] == "pending"


# --- migration from the old bot -------------------------------------------------------

async def test_old_state_is_kept(tmp_path):
    from bot.storage import Storage
    (tmp_path / "state.json").write_text(json.dumps({
        "last_update_id": 5, "known_users": {"1": {"source": "ybc_lisbon"}, "2": {}}}))
    s = Storage(tmp_path)
    assert s.users_from("ybc_lisbon") == [1]
    s.set_state("awaiting_edit_for", None)
    assert json.loads((tmp_path / "state.json").read_text())["last_update_id"] == 5


# --- business bingo (I AM. IN) -------------------------------------------------------------

def bingo_user(n: int):
    from aiogram.types import User
    return User(id=1000 + n, is_bot=False, first_name=f"G{n}", username=f"g{n}")


async def play(dp, bot, user, name, yes_with_story=(), final="Бублик"):
    """Go through the whole bingo as one guest."""
    await dp.feed_update(bot, press("src:iam:bingo", user=user))
    await dp.feed_update(bot, msg(name, user=user))
    for q in range(9):
        if q in yes_with_story:
            await dp.feed_update(bot, press(f"bingo:ans:{q}:y", user=user))
            await dp.feed_update(bot, msg(f"Історія {name} про питання {q + 1}", user=user))
        else:
            await dp.feed_update(bot, press(f"bingo:ans:{q}:n", user=user))
    if final:
        await dp.feed_update(bot, msg(final, user=user))


async def test_bingo_button_first_on_iam_screen(env, content):
    dp, bot, session, storage = env
    await dp.feed_update(bot, msg("/start iam_lisbon"))
    assert labels(session.to(CLIENT.id)[-1])[0] == content.bingo.button


async def test_bingo_guest_flow(env, content):
    dp, bot, session, storage = env
    await dp.feed_update(bot, press("src:iam:bingo"))
    assert session.to(CLIENT.id)[-1].text == content.bingo.ask_name
    await dp.feed_update(bot, msg("Олена Коваленко"))
    q1 = session.to(CLIENT.id)[-1]
    assert "Питання 1 з 9" in q1.text
    assert [r[0].text for r in q1.reply_markup.inline_keyboard] == [content.bingo.yes_button, content.bingo.no_button]

    await dp.feed_update(bot, press("bingo:ans:0:y"))
    assert session.to(CLIENT.id)[-1].text == content.bingo.story_prompt
    await dp.feed_update(bot, msg("Банк просив виписку за 5 років тричі"))
    card = session.to(MANAGER.id)[-1]
    assert "Питання 1" in card.text and "<b>Олена Коваленко</b>: «Банк просив виписку" in card.text
    assert "Питання 2 з 9" in session.to(CLIENT.id)[-1].text

    await dp.feed_update(bot, press("bingo:ans:0:n"))  # old button: ignored
    await dp.feed_update(bot, press("bingo:ans:1:y"))
    await dp.feed_update(bot, press("bingo:skip:1"))  # no story
    for q in range(2, 9):
        await dp.feed_update(bot, press(f"bingo:ans:{q}:n"))
    assert "Фінальне питання" in session.to(CLIENT.id)[-1].text
    await dp.feed_update(bot, msg("Бублик"))
    assert "Олена Коваленко" in session.to(CLIENT.id)[-1].text

    p = storage.get_state("bingo")[str(CLIENT.id)]
    assert p["answers"]["1"] == "yes" and p["answers"]["2"] == "yes" and p["answers"]["3"] == "no"
    assert list(p["stories"]) == ["1"] and p["final"] == "Бублик" and p["done_at"]
    # stories are not sent as normal "incoming" messages
    assert not any("Входящее" in m.text for m in session.to(MANAGER.id))

    await dp.feed_update(bot, press("src:iam:bingo"))
    assert "вже пройшли" in session.to(CLIENT.id)[-1].text


async def test_bingo_prizes_and_final_list(env, content):
    dp, bot, session, storage = env
    guests = [bingo_user(n) for n in range(15)]
    for n, g in enumerate(guests):
        await play(dp, bot, g, f"Гість {n}", yes_with_story=(0,) if n < 3 else (),
                   final="Бублик" if n < 12 else None)

    # Ksenia: 2 best stories (one mat, one bag)
    await dp.feed_update(bot, press(f"bingo:best:{guests[0].id}:0", user=MANAGER))
    choice = session.to(MANAGER.id)[-1]
    assert [r[0].text for r in choice.reply_markup.inline_keyboard][:2] == ["Мат для йоги (5)", "Спортивна сумка (5)"]
    await dp.feed_update(bot, press(f"bingo:bestgive:{guests[0].id}:0:yoga_mat", user=MANAGER))
    await dp.feed_update(bot, press(f"bingo:bestgive:{guests[1].id}:0:sport_bag", user=MANAGER))
    await dp.feed_update(bot, press(f"bingo:bestgive:{guests[1].id}:0:yoga_mat", user=MANAGER))  # 2nd for same: no

    # a gift "from THE A"
    await dp.feed_update(bot, msg("/gift Марія Шевченко", user=MANAGER))
    await dp.feed_update(bot, press("bingo:gift:tshirt", user=MANAGER))

    # draw: 3+3+4-1 = 9 items among guests without gifts (13 of them)
    await dp.feed_update(bot, press("bingo:draw", user=MANAGER))
    aw = storage.get_state("bingo_awards")
    drawn = [a for a in aw if a["pool"] == "draw"]
    assert len(drawn) == 9 and len({a["user_id"] for a in drawn}) == 9
    assert not {a["user_id"] for a in drawn} & {guests[0].id, guests[1].id}

    # final: audit + 8 leftover mats/bags among the 12 who answered the final question
    await dp.feed_update(bot, press("bingo:final", user=MANAGER))
    final = [a for a in storage.get_state("bingo_awards") if a["pool"] == "final"]
    assert final[0]["prize"] == "audit" and len(final) == 9
    assert {a["user_id"] for a in final} <= {g.id for g in guests[:12]}

    report = session.to(MANAGER.id)[-1].text
    assert report.startswith("<b>🏆 Бізнес-бінго · переможці</b>")
    for part in ("🎲 Розіграш", "🎁 Від THE A", "Марія Шевченко - Футболка", "📝 Найкращі історії",
                 "Гість 0 - Мат для йоги (питання 1)", "🏁 Фінальний розіграш", "Структурний аудит",
                 "улюбленець: Бублик"):
        assert part in report

    # nothing left to draw
    await dp.feed_update(bot, press("bingo:draw", user=MANAGER))
    assert len([a for a in storage.get_state("bingo_awards") if a["pool"] == "draw"]) == 9


async def test_bingo_undo_and_status(env, content):
    dp, bot, session, storage = env
    await play(dp, bot, bingo_user(1), "Гість 1", yes_with_story=(2,))
    await dp.feed_update(bot, press(f"bingo:bestgive:{bingo_user(1).id}:2:sport_bag", user=MANAGER))
    await dp.feed_update(bot, press("bingo:undo", user=MANAGER))
    assert storage.get_state("bingo_awards") == []
    await dp.feed_update(bot, msg("/bingo", user=MANAGER))
    status = session.to(MANAGER.id)[-1]
    assert "Учасників: 1" in status.text and "Спортивна сумка: 5 з 5" in status.text
    assert status.reply_markup.inline_keyboard[0][0].callback_data == "bingo:draw"
    await dp.feed_update(bot, msg("/bingo_answers 3", user=MANAGER))
    assert "Гість 1</b>: «Історія Гість 1 про питання 3»" in session.to(MANAGER.id)[-1].text


async def test_bingo_manager_buttons_only_for_manager(env):
    dp, bot, session, storage = env
    await play(dp, bot, CLIENT, "Олена")
    await dp.feed_update(bot, press("bingo:draw"))
    assert storage.get_state("bingo_awards") is None
