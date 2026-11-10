"""Loads and validates bot texts from content/texts.yaml."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


class Buttons(BaseModel):
    write_manager: str
    back: str
    cancel: str


class Photos(BaseModel):
    button: str
    album_button: str
    album_url: HttpUrl
    text: str


class Topic(BaseModel):
    id: str
    button: str
    text: str


class Consultation(BaseModel):
    button: str
    ask_name: str
    ask_contact: str
    share_contact_button: str
    ask_question: str
    done: str
    cancelled: str


class Manager(BaseModel):
    prompt: str
    sent: str


SPECIAL_BUTTONS = {"photos", "consult"}
DEFAULT_SCREEN = "default"


class ButtonRef(BaseModel):
    """A button on a start screen: "photos", "consult" or a topic id."""

    id: str
    label: str | None = None

    @model_validator(mode="before")
    @classmethod
    def from_string(cls, value):
        return {"id": value} if isinstance(value, str) else value


class Screen(BaseModel):
    text: str
    buttons: list[ButtonRef]


class Profile(BaseModel):
    description: str = Field(max_length=512)
    short_description: str = Field(max_length=120)


class Content(BaseModel):
    start_screens: dict[str, Screen]
    buttons: Buttons
    photos: Photos
    topics: list[Topic]
    consultation: Consultation
    manager: Manager
    profile: Profile
    commands: dict[str, str]

    @field_validator("topics")
    @classmethod
    def unique_topic_ids(cls, topics: list[Topic]) -> list[Topic]:
        ids = [t.id for t in topics]
        if len(ids) != len(set(ids)):
            raise ValueError(f"topic ids must be unique, got {ids}")
        return topics

    @model_validator(mode="after")
    def check_screens(self) -> "Content":
        if DEFAULT_SCREEN not in self.start_screens:
            raise ValueError(f"start_screens must contain '{DEFAULT_SCREEN}'")
        known = SPECIAL_BUTTONS | {t.id for t in self.topics}
        for name, screen in self.start_screens.items():
            for b in screen.buttons:
                if b.id not in known:
                    raise ValueError(f"screen '{name}': unknown button '{b.id}', expected one of {sorted(known)}")
        return self

    def screen(self, name: str | None) -> tuple[str, Screen]:
        """Screen by name, falling back to the default one."""
        key = name if name in self.start_screens else DEFAULT_SCREEN
        return key, self.start_screens[key]

    def topic(self, topic_id: str) -> Topic | None:
        return next((t for t in self.topics if t.id == topic_id), None)


def load_content(path: Path) -> Content:
    with path.open(encoding="utf-8") as f:
        return Content.model_validate(yaml.safe_load(f))
