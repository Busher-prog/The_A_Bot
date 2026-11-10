import pytest

from bot.content import Content
from bot.formatting import extract_client_id
from bot.keyboards import start_menu, topic_menu


def test_texts_file_is_valid(content):
    assert {"direct", "ybc", "iam", "relocate", "hayat"} <= set(content.screens)


def test_old_qr_links_still_known(content):
    for param in ("ybc_lisbon", "iam_lisbon", "relocate", "hayat_webinar_13jun"):
        key, screen = content.screen_by_start_param(param)
        assert screen.start_param == param


def test_ybc_menu_photos_first_consult_instead_of_raffle(content):
    rows = [r[0].text for r in start_menu(content, "ybc").inline_keyboard]
    assert rows[0] == content.buttons.photos
    assert content.buttons.consult in rows
    assert not any("Розіграш" in r for r in rows)


def test_callback_data_fits_telegram_limit(content):
    for key in content.screens:
        for kb in (start_menu(content, key), topic_menu(content, key)):
            for row in kb.inline_keyboard:
                assert len(row[0].callback_data.encode()) <= 64


def test_unknown_button_is_rejected(content):
    data = content.model_dump(mode="json")
    data["screens"]["direct"]["buttons"].append({"id": "seg_lottery"})
    with pytest.raises(ValueError, match="seg_lottery"):
        Content.model_validate(data)


def test_extract_client_id_new_and_old_cards():
    assert extract_client_id("Имя: X\nuser_id: 1\nchat_id: 777\n") == 777
    assert extract_client_id("🧮 ...\nchat_id: -100500") == -100500
    assert extract_client_id("no id") is None
