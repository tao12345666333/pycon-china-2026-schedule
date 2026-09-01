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

    if len(talks) != 46:
        raise ValueError(f"Expected 46 talks, found {len(talks)}")

    ids = [talk["id"] for talk in talks]
    if len(ids) != len(set(ids)):
        raise ValueError("Every talk id must be unique")

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

        duration = minutes(talk["end"]) - minutes(talk["start"])
        expected = talk["talk_minutes"] + talk["qa_minutes"]
        if duration != expected:
            raise ValueError(f"{talk['id']} occupies {duration} minutes, expected {expected}")

        if talk["period"] == "morning":
            if talk["track"] != "main" or talk["type"] != "standard":
                raise ValueError(f"{talk['id']} has an invalid morning placement")
            if talk["talk_minutes"] != 40 or talk["qa_minutes"] != 0:
                raise ValueError(f"{talk['id']} must be 40 minutes without QA")
        elif talk["period"] == "afternoon" and talk["type"] == "standard":
            if talk["track"] == "main":
                raise ValueError(f"{talk['id']} needs an afternoon breakout track")
            if talk["talk_minutes"] != 35 or talk["qa_minutes"] != 5:
                raise ValueError(f"{talk['id']} must be 35 minutes plus 5 minutes QA")
        elif talk["period"] == "afternoon" and talk["type"] == "lightning":
            if talk["talk_minutes"] != 10 or talk["qa_minutes"] != 0:
                raise ValueError(f"{talk['id']} must be a 10-minute lightning talk")
            if minutes(talk["start"]) < minutes(conference["lightning_start"]):
                raise ValueError(f"{talk['id']} must be in the final lightning block")
        else:
            raise ValueError(f"{talk['id']} has unsupported period/type values")

    morning_speakers = {talk["speaker"] for talk in talks if talk["period"] == "morning"}
    required_morning = {"周彦君", "刘晓国", "古思为"}
    if not required_morning <= morning_speakers:
        raise ValueError(f"Missing required morning speakers: {required_morning - morning_speakers}")

    registration = conference["registration"]
    if (registration["start"], registration["end"]) != ("09:00", "09:30"):
        raise ValueError("Registration must run from 09:00 to 09:30")

    tea_start = minutes(conference["tea_break"]["start"])
    tea_end = minutes(conference["tea_break"]["end"])
    if tea_end - tea_start != 20:
        raise ValueError("The afternoon tea break must be 20 minutes")

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
    breakouts = {}
    for track_id in ("A", "B", "C", "D", "E"):
        track_talks = [talk for talk in talks if talk["track"] == track_id]
        breakouts[track_id] = {
            "standard": sorted(
                (talk for talk in track_talks if talk["type"] == "standard"),
                key=lambda talk: minutes(talk["start"]),
            ),
            "lightning": sorted(
                (talk for talk in track_talks if talk["type"] == "lightning"),
                key=lambda talk: minutes(talk["start"]),
            ),
        }

    counts = defaultdict(int)
    for talk in talks:
        counts[talk["type"]] += 1

    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(("html", "xml")),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    html = env.get_template("index.html.j2").render(
        agenda=agenda,
        morning=morning,
        breakouts=breakouts,
        counts=counts,
    )

    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / "index.html").write_text(html, encoding="utf-8")
    shutil.copy2(ROOT / "assets" / "style.css", OUTPUT_DIR / "style.css")
    print(f"Built {OUTPUT_DIR / 'index.html'} with {len(talks)} talks")


if __name__ == "__main__":
    build()
