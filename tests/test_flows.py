from aiogram.types import Contact

from bot.keyboards import Menu
from tests.conftest import BOT_ID, CLIENT, MANAGERS_CHAT, make_callback, make_message


async def test_start_shows_welcome_and_menu(env, content):
    dp, bot, session = env
    await dp.feed_update(bot, make_message("/start"))
    msg = session.sent("SendMessage")[-1]
    assert msg.text == content.start_screens["default"].text
    assert msg.reply_markup.inline_keyboard[0][0].text == content.photos.button


async def test_qr_link_opens_event_screen_and_back_returns_there(env, content):
    dp, bot, session = env
    await dp.feed_update(bot, make_message("/start ybc"))
    msg = session.sent("SendMessage")[-1]
    assert msg.text == content.start_screens["ybc"].text
    labels = [row[0].text for row in msg.reply_markup.inline_keyboard]
    assert labels[0] == content.photos.button
    assert labels[-2:] == [content.consultation.button, "🤔 Інше"]

    # open a topic, press "back": we land on the event screen again, not the default one
    await dp.feed_update(bot, make_callback(Menu(action="topic", topic="tax", screen="ybc").pack()))
    back = session.sent("SendMessage")[-1].reply_markup.inline_keyboard[-1][0]
    await dp.feed_update(bot, make_callback(back.callback_data))
    assert session.sent("SendMessage")[-1].text == content.start_screens["ybc"].text


async def test_unknown_start_link_falls_back_to_default(env, content):
    dp, bot, session = env
    await dp.feed_update(bot, make_message("/start something-old"))
    assert session.sent("SendMessage")[-1].text == content.start_screens["default"].text


async def test_photos_button_sends_text_and_album_link(env, content):
    dp, bot, session = env
    await dp.feed_update(bot, make_callback(Menu(action="photos").pack()))
    msg = session.sent("SendMessage")[-1]
    assert msg.text == content.photos.text
    assert msg.reply_markup.inline_keyboard[0][0].url == str(content.photos.album_url)


async def test_topic_then_free_text_reaches_managers_with_topic(env, content):
    dp, bot, session = env
    await dp.feed_update(bot, make_callback(Menu(action="topic", topic="banks").pack()))
    await dp.feed_update(bot, make_message("Рахунок заблокували"))
    to_managers = [m for m in session.sent("SendMessage") if m.chat_id == MANAGERS_CHAT]
    assert len(to_managers) == 1
    assert "#id777" in to_managers[0].text
    assert "Банки і рахунки" in to_managers[0].text
    assert "Рахунок заблокували" in to_managers[0].text
    assert session.sent("SendMessage")[-1].text == content.manager.sent


async def test_old_command_shows_menu_instead_of_going_to_managers(env, content):
    dp, bot, session = env
    await dp.feed_update(bot, make_message("/calculator"))
    sent = session.sent("SendMessage")
    assert all(m.chat_id != MANAGERS_CHAT for m in sent)
    assert sent[-1].text == content.start_screens["default"].text


async def test_manager_reply_is_delivered_to_client(env):
    dp, bot, session = env
    from aiogram.types import Chat, Message, User
    import datetime
    header = Message(message_id=5, date=datetime.datetime.now(),
                     chat=Chat(id=MANAGERS_CHAT, type="supergroup"),
                     from_user=User(id=BOT_ID, is_bot=True, first_name="bot"),
                     text="📩 Повідомлення від клієнта\n👤 Olena @olena · #id777\n\nhi")
    manager = User(id=1, is_bot=False, first_name="Manager")
    await dp.feed_update(bot, make_message("Добрий день!", user=manager, chat_id=MANAGERS_CHAT,
                                           chat_type="supergroup", reply_to=header))
    copies = session.sent("CopyMessage")
    assert len(copies) == 1 and copies[0].chat_id == CLIENT.id


async def test_consultation_flow_creates_lead(env, content):
    dp, bot, session = env
    await dp.feed_update(bot, make_callback(Menu(action="consult").pack()))
    await dp.feed_update(bot, make_message("Олена"))
    await dp.feed_update(bot, make_message(contact=Contact(phone_number="+351900000000",
                                                           first_name="Olena", user_id=777)))
    await dp.feed_update(bot, make_message("Резидентство в Португалії"))

    leads = [m for m in session.sent("SendMessage") if m.chat_id == MANAGERS_CHAT]
    assert len(leads) == 1
    for part in ("Заявка на консультацію", "Олена", "+351900000000", "Резидентство", "#id777"):
        assert part in leads[0].text
    assert content.consultation.done in [m.text for m in session.sent("SendMessage")]


async def test_consultation_can_be_cancelled(env, content):
    dp, bot, session = env
    await dp.feed_update(bot, make_message("/consult"))
    await dp.feed_update(bot, make_message(content.buttons.cancel))
    await dp.feed_update(bot, make_message("просто питання"))  # back to normal mode
    to_managers = [m for m in session.sent("SendMessage") if m.chat_id == MANAGERS_CHAT]
    assert len(to_managers) == 1 and "Заявка" not in to_managers[0].text
