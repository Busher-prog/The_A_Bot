"""Loads and validates bot texts from content/texts.yaml."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, HttpUrl, model_validator

DEFAULT_SCREEN = "direct"


class Settings(BaseModel):
    timezone: str = "Europe/Berlin"
    work_start: int = 10
    work_end: int = 22


class Button(BaseModel):
    """A button on a start screen or under a topic.

    id: photos | consult | calc | discuss | menu | form_<form> | seg_<topic>
    """

    id: str
    label: str | None = None

    @model_validator(mode="before")
    @classmethod
    def from_string(cls, value):
        return {"id": value} if isinstance(value, str) else value


class Screen(BaseModel):
    start_param: str | None = None
    label: str  # shown to managers: where the client came from
    lead_title: str  # title of lead cards for managers
    group: str  # which topic group the seg_ buttons refer to
    text: str
    buttons: list[Button]


class Topic(BaseModel):
    label: str
    text: str


class Group(BaseModel):
    topic_buttons: list[Button]
    discuss_text: str | None = None
    topics: dict[str, Topic]


class FormStep(BaseModel):
    key: str
    label: str  # field name in the lead card
    prompt: str  # may use {answers[<key>]} of previous steps
    share_contact_button: str | None = None


class Form(BaseModel):
    lead_title: str
    log_file: str
    intro: str | None = None
    steps: list[FormStep] = Field(min_length=1)
    done: str
    cancelled: str
    extra: dict[str, str] = {}


class BingoCell(BaseModel):
    short: str = Field(max_length=20)
    text: str


class Prize(BaseModel):
    id: str
    label: str
    qty: int = Field(ge=0)


class Bingo(BaseModel):
    button: str
    intro: str
    cells: list[BingoCell] = Field(min_length=9, max_length=9)
    story_prompt: str
    skip_button: str
    story_saved: str
    bingo_text: str
    full_text: str
    winner_text: str
    prizes: list[Prize]


class Buttons(BaseModel):
    cancel: str
    photos: str
    consult: str


class Photos(BaseModel):
    album_button: str
    album_url: HttpUrl
    text: str


class Replies(BaseModel):
    ack_work: str
    ack_off: str


class Profile(BaseModel):
    description: str = Field(max_length=512)
    short_description: str = Field(max_length=120)


class Content(BaseModel):
    settings: Settings = Settings()
    screens: dict[str, Screen]
    groups: dict[str, Group]
    buttons: Buttons
    photos: Photos
    forms: dict[str, Form]
    bingo: Bingo
    replies: Replies
    commands_text: dict[str, str]
    profile: Profile
    commands: dict[str, str]

    @model_validator(mode="after")
    def check_references(self) -> "Content":
        if DEFAULT_SCREEN not in self.screens:
            raise ValueError(f"screens must contain '{DEFAULT_SCREEN}'")
        params = [s.start_param for s in self.screens.values() if s.start_param]
        if len(params) != len(set(params)):
            raise ValueError("start_param values must be unique")
        if "consult" not in self.forms:
            raise ValueError("forms must contain 'consult'")
        for name, screen in self.screens.items():
            if screen.group not in self.groups:
                raise ValueError(f"screen '{name}': unknown group '{screen.group}'")
            for b in screen.buttons:
                self._check_button(f"screen '{name}'", b, screen.group)
            for b in self.groups[screen.group].topic_buttons:
                self._check_button(f"group '{screen.group}'", b, screen.group)
        return self

    def _check_button(self, where: str, b: Button, group: str) -> None:
        if b.id in {"photos", "consult", "calc", "discuss", "menu", "bingo"}:
            return
        if b.id.startswith("form_") and b.id[5:] in self.forms:
            return
        if b.id.startswith("seg_") and b.id[4:] in self.groups[group].topics:
            return
        raise ValueError(f"{where}: unknown button '{b.id}'")

    # --- lookups -----------------------------------------------------------

    def screen(self, key: str | None) -> tuple[str, Screen]:
        key = key if key in self.screens else DEFAULT_SCREEN
        return key, self.screens[key]

    def screen_by_start_param(self, param: str | None) -> tuple[str, Screen]:
        for key, s in self.screens.items():
            if param and s.start_param == param:
                return key, s
        return DEFAULT_SCREEN, self.screens[DEFAULT_SCREEN]

    def group_of(self, screen_key: str) -> Group:
        return self.groups[self.screen(screen_key)[1].group]


def load_content(path: Path) -> Content:
    with path.open(encoding="utf-8") as f:
        return Content.model_validate(yaml.safe_load(f))
