#!/usr/bin/env python3
from __future__ import annotations

import shutil
from collections import defaultdict
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "agenda.yaml"
OUTPUT_DIR = ROOT / "site"


def minutes(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid time: {value}")
    return hour * 60 + minute


def validate(agenda: dict) -> None:
    conference = agenda["conference"]
    tracks = agenda["tracks"]
    talks = agenda["talks"]

    conference_start = minutes(conference["start"])
    conference_end = minutes(conference["end"])
    lightning_start = minutes(conference["lightning_start"])
    if conference_start >= conference_end:
        raise ValueError("Conference start must be earlier than conference end")
    if "main" not in tracks:
        raise ValueError("The main track is required")
    if not any(track_id != "main" for track_id in tracks):
        raise ValueError("At least one breakout track is required")

    ids = [talk["id"] for talk in talks]
    if len(ids) != len(set(ids)):
        raise ValueError("Every talk id must be unique")

    for slot_name in ("registration", "lunch", "tea_break"):
        slot = conference[slot_name]
        slot_start = minutes(slot["start"])
        slot_end = minutes(slot["end"])
        if slot_start >= slot_end:
            raise ValueError(f"{slot_name} start must be earlier than its end")
        if slot_start < conference_start or slot_end > conference_end:
            raise ValueError(f"{slot_name} must be within conference hours")

    registration = conference["registration"]
    lunch = conference["lunch"]
    tea_break = conference["tea_break"]
    if minutes(registration["end"]) > minutes(lunch["start"]):
        raise ValueError("Registration must end before lunch starts")
    if minutes(lunch["end"]) > minutes(tea_break["start"]):
        raise ValueError("Lunch must end before the tea break starts")
    if not minutes(lunch["end"]) <= lightning_start < conference_end:
        raise ValueError("Lightning talks must start after lunch and before conference end")

    required_fields = {
        "id",
        "speaker",
        "speaker_en",
        "role",
        "title",
        "title_en",
        "type",
        "period",
        "track",
        "start",
        "end",
        "talk_minutes",
        "qa_minutes",
    }
    for talk in talks:
        missing = required_fields - talk.keys()
        if missing:
            raise ValueError(f"{talk.get('id', '<unknown>')} is missing: {sorted(missing)}")
        if not talk["title"].strip() or not talk["title_en"].strip():
            raise ValueError(f"{talk['id']} must have Chinese and English titles")
        if talk["track"] not in tracks:
            raise ValueError(f"{talk['id']} uses unknown track {talk['track']}")

        talk_start = minutes(talk["start"])
        talk_end = minutes(talk["end"])
        duration = talk_end - talk_start
        expected = talk["talk_minutes"] + talk["qa_minutes"]
        if talk_start < conference_start or talk_end > conference_end:
            raise ValueError(f"{talk['id']} must be within conference hours")
        if talk["talk_minutes"] <= 0 or talk["qa_minutes"] < 0:
            raise ValueError(f"{talk['id']} has invalid talk or QA minutes")
        if duration != expected:
            raise ValueError(f"{talk['id']} occupies {duration} minutes, expected {expected}")

        if talk["period"] == "morning":
            if talk["track"] != "main" or talk["type"] != "standard":
                raise ValueError(f"{talk['id']} has an invalid morning placement")
            if talk_start < minutes(registration["end"]) or talk_end > minutes(lunch["start"]):
                raise ValueError(f"{talk['id']} must be between registration and lunch")
        elif talk["period"] == "afternoon" and talk["type"] == "standard":
            if talk["track"] == "main":
                raise ValueError(f"{talk['id']} needs an afternoon breakout track")
            if talk_start < minutes(lunch["end"]):
                raise ValueError(f"{talk['id']} must start after lunch")
        elif talk["period"] == "afternoon" and talk["type"] == "lightning":
            if talk["track"] == "main":
                raise ValueError(f"{talk['id']} needs an afternoon breakout track")
            if talk_start < lightning_start:
                raise ValueError(f"{talk['id']} must be in the final lightning block")
        else:
            raise ValueError(f"{talk['id']} has unsupported period/type values")

    morning = [talk for talk in talks if talk["period"] == "morning"]
    afternoon = [talk for talk in talks if talk["period"] == "afternoon"]
    lightning = [talk for talk in afternoon if talk["type"] == "lightning"]
    if not morning:
        raise ValueError("At least one morning talk is required")
    if not afternoon:
        raise ValueError("At least one afternoon talk is required")
    if not lightning:
        raise ValueError("At least one lightning talk is required")
    if min(minutes(talk["start"]) for talk in lightning) != lightning_start:
        raise ValueError("The first lightning talk must match conference.lightning_start")

    tea_start = minutes(tea_break["start"])
    tea_end = minutes(tea_break["end"])

    for track_id in tracks:
        track_talks = sorted(
            (talk for talk in talks if talk["track"] == track_id),
            key=lambda talk: minutes(talk["start"]),
        )
        for previous, current in zip(track_talks, track_talks[1:]):
            if minutes(current["start"]) < minutes(previous["end"]):
                raise ValueError(
                    f"Track {track_id} overlap: {previous['id']} and {current['id']}"
                )
        track_standard = [talk for talk in track_talks if talk["type"] == "standard"]
        track_lightning = [talk for talk in track_talks if talk["type"] == "lightning"]
        if track_standard and track_lightning:
            if max(minutes(talk["end"]) for talk in track_standard) > min(
                minutes(talk["start"]) for talk in track_lightning
            ):
                raise ValueError(f"Track {track_id} must place lightning talks last")
        if track_id != "main":
            for talk in track_talks:
                if minutes(talk["start"]) < tea_end and minutes(talk["end"]) > tea_start:
                    raise ValueError(f"{talk['id']} overlaps the tea break")


def build() -> None:
    agenda = yaml.safe_load(DATA_FILE.read_text(encoding="utf-8"))
    validate(agenda)

    talks = agenda["talks"]
    morning = sorted(
        (talk for talk in talks if talk["period"] == "morning"),
        key=lambda talk: minutes(talk["start"]),
    )
    track_ids = [track_id for track_id in agenda["tracks"] if track_id != "main"]
    tea_start = minutes(agenda["conference"]["tea_break"]["start"])
    tea_end = minutes(agenda["conference"]["tea_break"]["end"])
    breakouts = {}
    for track_id in track_ids:
        track_talks = [talk for talk in talks if talk["track"] == track_id]
        standard = sorted(
            (talk for talk in track_talks if talk["type"] == "standard"),
            key=lambda talk: minutes(talk["start"]),
        )
        breakouts[track_id] = {
            "standard_before_break": [
                talk for talk in standard if minutes(talk["end"]) <= tea_start
            ],
            "standard_after_break": [
                talk for talk in standard if minutes(talk["start"]) >= tea_end
            ],
            "lightning": sorted(
                (talk for talk in track_talks if talk["type"] == "lightning"),
                key=lambda talk: minutes(talk["start"]),
            ),
        }

    counts = defaultdict(int)
    for talk in talks:
        counts[talk["type"]] += 1

    afternoon = [talk for talk in talks if talk["period"] == "afternoon"]
    lightning = [talk for talk in afternoon if talk["type"] == "lightning"]
    schedule = {
        "registration_minutes": minutes(agenda["conference"]["registration"]["end"])
        - minutes(agenda["conference"]["registration"]["start"]),
        "lunch_minutes": minutes(agenda["conference"]["lunch"]["end"])
        - minutes(agenda["conference"]["lunch"]["start"]),
        "tea_break_minutes": tea_end - tea_start,
        "morning_start": morning[0]["start"],
        "morning_end": morning[-1]["end"],
        "afternoon_start": min(afternoon, key=lambda talk: minutes(talk["start"]))["start"],
        "afternoon_end": max(afternoon, key=lambda talk: minutes(talk["end"]))["end"],
        "lightning_start": agenda["conference"]["lightning_start"],
        "lightning_tracks": [
            track_id
            for track_id in track_ids
            if any(talk["track"] == track_id for talk in lightning)
        ],
    }

    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(default=True),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    html = env.get_template("index.html.j2").render(
        agenda=agenda,
        morning=morning,
        breakouts=breakouts,
        counts=counts,
        schedule=schedule,
        track_ids=track_ids,
    )

    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / "index.html").write_text(html, encoding="utf-8")
    shutil.copy2(ROOT / "assets" / "style.css", OUTPUT_DIR / "style.css")
    print(f"Built {OUTPUT_DIR / 'index.html'} with {len(talks)} talks")


if __name__ == "__main__":
    build()
