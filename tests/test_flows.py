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
