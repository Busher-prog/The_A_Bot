"""Loads and validates bot texts from content/texts.yaml."""

from pathlib import Path

import yaml
from pydantic import BaseModel, HttpUrl, field_validator


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


class Content(BaseModel):
    welcome: str
    buttons: Buttons
    photos: Photos
    topics: list[Topic]
    consultation: Consultation
    manager: Manager
    commands: dict[str, str]

    @field_validator("topics")
    @classmethod
    def unique_topic_ids(cls, topics: list[Topic]) -> list[Topic]:
        ids = [t.id for t in topics]
        if len(ids) != len(set(ids)):
            raise ValueError(f"topic ids must be unique, got {ids}")
        return topics

    def topic(self, topic_id: str) -> Topic | None:
        return next((t for t in self.topics if t.id == topic_id), None)


def load_content(path: Path) -> Content:
    with path.open(encoding="utf-8") as f:
        return Content.model_validate(yaml.safe_load(f))
