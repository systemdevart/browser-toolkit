#!/usr/bin/env python3
"""Build a French-to-Russian beginner vocabulary quiz.

The source list is the frequency-ranked A1 section of Vocabcraft's French deck,
published under CC BY-SA 4.0. Simple pronunciation respellings are preserved
verbatim; OpenAI adds Russian translations, distractors, and short A1 examples.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path

import requests

from vocab_builder import (
    DEFAULT_MODEL,
    HTTP_USER_AGENT,
    ROOT,
    call_openai,
    read_existing_vocab,
    write_vocab_js,
)


DEFAULT_SOURCE_URL = "https://vocabcraft.com/decks/french"
DEFAULT_COUNT = 1000
MAX_A1_WORDS = 1173
BATCH_SIZE = 40


def _plain_punctuation(value: str) -> str:
    return value.translate(
        str.maketrans(
            {
                "«": '"',
                "»": '"',
                "“": '"',
                "”": '"',
                "„": '"',
                "‘": "'",
                "’": "'",
            }
        )
    )


class FrenchDeckParser(HTMLParser):
    """Extract rendered word cards without parsing Next.js internals."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[dict[str, str]] = []
        self.current: dict[str, str] | None = None
        self.capture: str | None = None
        self.capture_depth = 0
        self.buffer: list[str] = []

    @staticmethod
    def _attributes(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key: value or "" for key, value in attrs}

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = self._attributes(attrs)
        if tag == "a" and attributes.get("href", "").startswith(
            "/decks/french/"
        ):
            self.current = {}
            return
        if self.current is None:
            return
        if self.capture:
            self.capture_depth += 1
            return
        classes = set(attributes.get("class", "").split())
        if tag == "span" and {"font-medium", "text-text-primary"} <= classes:
            self._start_capture("word")
        elif (
            tag == "span"
            and self.current.get("word")
            and "pronunciation" not in self.current
            and {"text-xs", "text-text-tertiary"} <= classes
        ):
            self._start_capture("pronunciation")
        elif tag == "div" and {
            "text-sm",
            "text-text-tertiary",
            "truncate",
        } <= classes:
            self._start_capture("definition")

    def _start_capture(self, field: str) -> None:
        self.capture = field
        self.capture_depth = 1
        self.buffer = []

    def handle_data(self, data: str) -> None:
        if self.capture:
            self.buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.current is None:
            return
        if self.capture:
            self.capture_depth -= 1
            if self.capture_depth == 0:
                value = " ".join("".join(self.buffer).split())
                if value:
                    self.current[self.capture] = _plain_punctuation(value)
                self.capture = None
                self.buffer = []
        if tag == "a" and self.capture is None:
            if all(
                self.current.get(field)
                for field in ("word", "pronunciation", "definition")
            ):
                self.entries.append(self.current)
            self.current = None


def fetch_beginner_entries(url: str, count: int) -> list[dict[str, str]]:
    response = requests.get(
        url,
        timeout=60,
        headers={"User-Agent": HTTP_USER_AGENT},
    )
    response.raise_for_status()
    parser = FrenchDeckParser()
    parser.feed(response.text)
    entries = parser.entries[:count]
    if len(entries) != count:
        raise RuntimeError(
            f"Expected {count} French A1 entries, found {len(entries)}"
        )
    words = [entry["word"].casefold() for entry in entries]
    if len(set(words)) != count:
        raise RuntimeError("The French A1 source contains duplicate headwords")
    return entries


def build_french_prompt(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    source_entries = [
        {
            "word": entry["word"],
            "simplePronunciation": entry["pronunciation"],
            "englishExplanation": entry["definition"],
        }
        for entry in entries
    ]
    return [
        {
            "role": "system",
            "content": (
                "You create French-to-Russian vocabulary cards for a complete "
                "beginner. Return strict JSON only. Use the supplied basic meaning, "
                "not an obscure secondary sense. The correct answer and every wrong "
                "answer must be written in Russian Cyrillic, never in French or "
                "English. Use only straight ASCII quotes and apostrophes."
            ),
        },
        {
            "role": "user",
            "content": (
                "Create one card for every source entry, in the same order. Keep each "
                "French word exactly as supplied. For each card return: `word`; "
                "`correct`, a concise Russian translation for the supplied beginner "
                "sense; `wrong`, exactly three distinct Russian distractors of the "
                "same part of speech which are not synonyms; and `examples`, exactly "
                "one short natural A1 French sentence using the supplied headword or "
                "its natural conjugated or inflected form. Do not add pronunciation "
                "because it is source-controlled.\n\n"
                "Return this shape: "
                '{"items":[{"word":"...","correct":"...",'
                '"wrong":["...","...","..."],"examples":["..."]}]}\n\n'
                "Source entries:\n"
                + json.dumps(source_entries, ensure_ascii=False)
            ),
        },
    ]


def normalize_french_item(
    raw: object,
    source: dict[str, str],
) -> dict | None:
    if not isinstance(raw, dict):
        return None
    word = _plain_punctuation(str(raw.get("word") or "").strip())
    if word.casefold() != source["word"].casefold():
        return None
    correct = _plain_punctuation(str(raw.get("correct") or "").strip())
    wrong = [
        _plain_punctuation(str(value).strip())
        for value in (raw.get("wrong") or [])
        if str(value).strip()
    ]
    examples = [
        _plain_punctuation(str(value).strip())
        for value in (raw.get("examples") or [])
        if str(value).strip()
    ]
    if not re.search(r"[А-Яа-яЁё]", correct):
        return None
    if any(not re.search(r"[А-Яа-яЁё]", value) for value in wrong):
        return None
    if len(wrong) != 3 or len({value.casefold() for value in wrong}) != 3:
        return None
    if correct.casefold() in {value.casefold() for value in wrong}:
        return None
    if len(examples) != 1:
        return None
    return {
        "word": source["word"],
        "base": source["word"],
        "pronunciation": source["pronunciation"],
        "correct": correct,
        "wrong": wrong,
        "examples": examples,
    }


def enrich_batch(
    entries: list[dict[str, str]],
    api_key: str,
    model: str,
) -> list[dict]:
    pending = {entry["word"].casefold(): entry for entry in entries}
    generated: dict[str, dict] = {}
    for attempt in range(1, 5):
        if not pending:
            break
        requested = list(pending.values())
        print(
            f"        attempt {attempt}: requesting {len(requested)} card(s)",
            flush=True,
        )
        data = call_openai(build_french_prompt(requested), api_key, model)
        raw_items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(raw_items, list):
            time.sleep(2)
            continue
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            key = str(raw.get("word") or "").strip().casefold()
            source = pending.get(key)
            if not source:
                continue
            item = normalize_french_item(raw, source)
            if item:
                generated[key] = item
        pending = {
            key: entry for key, entry in pending.items() if key not in generated
        }
        if pending:
            print(
                "        retrying invalid or missing: "
                + ", ".join(entry["word"] for entry in pending.values()),
                flush=True,
            )
            time.sleep(2)
    if pending:
        raise RuntimeError(
            "Could not generate valid cards for: "
            + ", ".join(entry["word"] for entry in pending.values())
        )
    return [generated[entry["word"].casefold()] for entry in entries]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--out", default="src/js/vocab-fr-basic.js")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    if not 1 <= args.count <= MAX_A1_WORDS:
        print(
            f"ERROR: --count must be between 1 and {MAX_A1_WORDS}",
            file=sys.stderr,
        )
        return 1
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY missing from .env", file=sys.stderr)
        return 1

    print(f"[1/3] Fetching {args.count} ranked French A1 words...")
    entries = fetch_beginner_entries(args.source_url, args.count)
    out_path = (ROOT / args.out).resolve()
    _, existing_items = read_existing_vocab(out_path)
    source_by_word = {
        entry["word"].casefold(): entry for entry in entries
    }
    items_by_word: dict[str, dict] = {}
    for item in existing_items:
        if not isinstance(item, dict) or not item.get("word"):
            continue
        key = str(item["word"]).casefold()
        source = source_by_word.get(key)
        if not source:
            continue
        normalized = normalize_french_item(item, source)
        if normalized:
            items_by_word[key] = normalized
    missing = [
        entry for entry in entries if entry["word"].casefold() not in items_by_word
    ]
    print(
        f"[2/3] Enriching {len(missing)} missing cards with {args.model} "
        f"({len(items_by_word)} already cached)..."
    )
    total_batches = (len(missing) + BATCH_SIZE - 1) // BATCH_SIZE
    for start in range(0, len(missing), BATCH_SIZE):
        batch = missing[start : start + BATCH_SIZE]
        batch_number = start // BATCH_SIZE + 1
        print(
            f"      batch {batch_number}/{total_batches}: {len(batch)} words",
            flush=True,
        )
        for item in enrich_batch(batch, api_key, args.model):
            items_by_word[item["word"].casefold()] = item
        ordered_partial = [
            items_by_word[entry["word"].casefold()]
            for entry in entries
            if entry["word"].casefold() in items_by_word
        ]
        write_vocab_js(
            {
                "id": "french-a1-basic-1000",
                "name": "French A1 - 1,000 basic words",
                "speechLang": "fr-FR",
                "speechLabel": "French",
                "speechRate": 0.82,
                "exampleLabel": "Example in French",
                "sourceUrl": args.source_url,
                "attribution": "Vocabcraft French A1 deck",
                "license": "CC BY-SA 4.0",
                "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
            },
            ordered_partial,
            out_path,
        )
        print(
            f"      saved checkpoint: {len(ordered_partial)}/{args.count}",
            flush=True,
        )

    items = [items_by_word[entry["word"].casefold()] for entry in entries]
    try:
        display_path = out_path.relative_to(ROOT)
    except ValueError:
        display_path = out_path
    print(f"[3/3] Writing {len(items)} cards to {display_path}")
    write_vocab_js(
        {
            "id": "french-a1-basic-1000",
            "name": "French A1 - 1,000 basic words",
            "speechLang": "fr-FR",
            "speechLabel": "French",
            "speechRate": 0.82,
            "exampleLabel": "Example in French",
            "sourceUrl": args.source_url,
            "attribution": "Vocabcraft French A1 deck",
            "license": "CC BY-SA 4.0",
            "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        },
        items,
        out_path,
    )
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
