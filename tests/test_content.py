from bot.formatting import extract_client_id
from bot.keyboards import main_menu


def test_texts_file_is_valid(content):
    assert content.topics, "at least one topic expected"
    assert "{name}" in content.consultation.ask_contact


def test_default_menu_photos_first_consultation_last(content):
    labels = [row[0].text for row in main_menu(content).inline_keyboard]
    assert labels[0] == content.photos.button
    assert labels[1:-1] == [t.button for t in content.topics]
    assert labels[-1] == content.consultation.button


def test_callback_data_fits_telegram_limit(content):
    for name in content.start_screens:
        for row in main_menu(content, name).inline_keyboard:
            assert len(row[0].callback_data.encode()) <= 64


def test_unknown_button_in_screen_is_rejected(content):
    import pytest
    from bot.content import Content
    data = content.model_dump(mode="json")
    data["start_screens"]["default"]["buttons"].append({"id": "lottery"})
    with pytest.raises(ValueError, match="lottery"):
        Content.model_validate(data)


def test_extract_client_id():
    assert extract_client_id("👤 Olena @olena · #id777\nTema") == 777
    assert extract_client_id("no tag") is None
    assert extract_client_id(None) is None
