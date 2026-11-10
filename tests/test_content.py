from bot.formatting import extract_client_id
from bot.keyboards import main_menu


def test_texts_file_is_valid(content):
    assert content.topics, "at least one topic expected"
    assert "{name}" in content.consultation.ask_contact


def test_menu_order_photos_first_consultation_last(content):
    rows = main_menu(content).inline_keyboard
    labels = [row[0].text for row in rows]
    assert labels[0] == content.photos.button
    assert labels[1:-1] == [t.button for t in content.topics]
    assert labels[-1] == content.consultation.button


def test_callback_data_fits_telegram_limit(content):
    for row in main_menu(content).inline_keyboard:
        assert len(row[0].callback_data.encode()) <= 64


def test_extract_client_id():
    assert extract_client_id("👤 Olena @olena · #id777\nTema") == 777
    assert extract_client_id("no tag") is None
    assert extract_client_id(None) is None
