#!/usr/bin/env python3
"""Generate PTE-style "Repeat Sentence" practice items with matching audio.

Pipeline:
  1. Ask GPT-5.6 Terra to write PTE-style academic English sentences.
  2. Speak each sentence with ElevenLabs, rotating through a curated set of
     premade voices (UK/US/AU, mix of genders) so consecutive items don't
     sound identical.

Outputs:
  site/public/repeat-sentence/problems.json
  site/public/repeat-sentence/sentence-01.mp3 ... sentence-NN.mp3

Run:
  .venv/bin/python scripts/repeat_sentence_builder.py --count 20
  .venv/bin/python scripts/repeat_sentence_builder.py --reuse-sentences

`--reuse-sentences` reads the existing problems.json and only regenerates the
audio, which is useful when you want to change voices or TTS provider without
throwing away the curated sentence list.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_LLM = "gpt-5.6-terra"

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
DEFAULT_TTS_MODEL = "eleven_multilingual_v2"

# Curated rotation of premade ElevenLabs voices — deliberate variety across
# accent (UK / US / AU) and gender so each sentence sounds different.
VOICE_ROTATION = [
    ("JBFqnCBsd6RMkjVDRZzb", "George",  "british"),
    ("EXAVITQu4vr4xnSDxMaL", "Sarah",   "american"),
    ("IKne3meq5aSn9XLyUdCD", "Charlie", "australian"),
    ("Xb7hH8MSUJpSbSDYk0k2", "Alice",   "british"),
    ("CwhRBWXzGAHq8TQ4Fs17", "Roger",   "american"),
    ("pFZP5JQG7iQjIQuC4Bku", "Lily",    "british"),
    ("onwK4e9ZLuTAKqWW03F9", "Daniel",  "british"),
    ("cgSgspJ2msm6clMCkdW9", "Jessica", "american"),
    ("nPczCjzI2devNBz1zQrb", "Brian",   "american"),
    ("XrExE9yKIg1WjnnlVkGX", "Matilda", "american"),
]


# ---------------------------------------------------------------------------
# OpenAI helpers
# ---------------------------------------------------------------------------

def _extract_json(content: str) -> dict:
    import re

    text = content.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```\s*$", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    return json.loads(text)


def _response_text(payload: dict) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    parts: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if (
                isinstance(content, dict)
                and content.get("type") == "output_text"
                and isinstance(content.get("text"), str)
            ):
                parts.append(content["text"])
    return "".join(parts)


def openai_json(messages: list[dict], api_key: str, model: str) -> dict:
    body = {
        "model": model,
        "input": messages,
        "reasoning": {"effort": "low"},
        "text": {"format": {"type": "json_object"}},
        "max_output_tokens": 8_000,
        "store": False,
    }
    resp = requests.post(
        OPENAI_RESPONSES_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=240,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"OpenAI error {resp.status_code}: {resp.text[:500]}")
    payload = resp.json()
    return _extract_json(_response_text(payload))


def elevenlabs_tts_mp3(
    text: str,
    api_key: str,
    voice_id: str,
    model_id: str,
) -> bytes:
    resp = requests.post(
        ELEVENLABS_TTS_URL.format(voice_id=voice_id),
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        json={
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True,
            },
        },
        timeout=180,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"ElevenLabs TTS error {resp.status_code}: {resp.text[:500]}"
        )
    if not resp.content:
        raise RuntimeError("ElevenLabs returned an empty body")
    return resp.content


# ---------------------------------------------------------------------------
# Sentence generation
# ---------------------------------------------------------------------------

DIFFICULTY_SPECS = {
    "easy": {
        "length": "between 8 and 14 words",
        "structure": "one clear main clause, one straightforward subordinate at most",
        "vocab": "concrete, everyday academic vocabulary — nothing abstract or technical",
        "topics": (
            "campus admin (library hours, cafeteria, orientation, timetables, "
            "shuttles, printing credits, scholarships, assignments, seminars, "
            "tutorials, student services, health centre, bookstore)"
        ),
    },
    "medium": {
        "length": "between 12 and 18 words",
        "structure": (
            "one main clause plus one clear subordinate (relative, adverbial "
            "or conditional); occasional coordination is fine"
        ),
        "vocab": (
            "slightly elevated academic vocabulary — some abstract nouns and "
            "content-area terms (methodology, hypothesis, sustainability, "
            "collaboration, funding, curriculum), but avoid jargon"
        ),
        "topics": (
            "broader academic life: research findings, policy debates in "
            "education, environmental studies, history topics, "
            "cross-disciplinary programmes, publication and peer review, "
            "conferences, ethics, statistics, teaching methods"
        ),
    },
    "hard": {
        "length": "between 15 and 22 words",
        "structure": (
            "one main clause with two subordinates (relative + adverbial, "
            "or conditional + concessive); passive voice permitted"
        ),
        "vocab": (
            "advanced academic register with field-specific but recognisable "
            "terms; nominalisation and abstract nouns are welcome"
        ),
        "topics": (
            "specialist academic content: epistemology, econometrics, "
            "molecular biology, jurisprudence, urban planning, cognitive "
            "psychology, climate modelling — still domain-general enough for "
            "a competent non-specialist listener"
        ),
    },
}


def build_sentence_prompt(count: int, difficulty: str, seen_sentences: list[str]) -> list[dict]:
    spec = DIFFICULTY_SPECS[difficulty]
    system = (
        "You author practice items for the PTE Academic \"Repeat Sentence\" task. "
        "Return STRICT JSON only, no prose."
    )
    avoid = ""
    if seen_sentences:
        joined = "\n".join(f"  - {s}" for s in seen_sentences)
        avoid = (
            f"\n\nAvoid generating sentences that overlap in meaning or "
            f"phrasing with the following already-used items:\n{joined}\n"
        )
    user = (
        f"Write {count} original single sentences suitable for the PTE Academic "
        f"\"Repeat Sentence\" task, at DIFFICULTY LEVEL: {difficulty}.\n\n"
        f"Requirements for each sentence:\n"
        f"  - length: {spec['length']}\n"
        f"  - structure: {spec['structure']}\n"
        f"  - vocabulary: {spec['vocab']}\n"
        f"  - topics: {spec['topics']}\n"
        f"  - factual/instructional tone; no questions; no shouted imperatives\n"
        f"  - no proper nouns, no ambiguous homophones, no digits\n"
        f"  - vary the topic and structure across the batch — do not "
        f"reuse the same subject twice in a row\n"
        f"{avoid}\n"
        f'Return this exact JSON shape:\n'
        f'{{"items": ["Sentence one.", "Sentence two.", ...]}}\n\n'
        f"Exactly {count} sentences. No duplicates. No commentary."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def generate_sentences(
    count: int,
    api_key: str,
    model: str,
    difficulty: str = "easy",
    already_seen: list[str] | None = None,
) -> list[str]:
    already_seen = already_seen or []
    seen_lower = {s.lower() for s in already_seen}
    data = openai_json(
        build_sentence_prompt(count, difficulty, already_seen), api_key, model
    )
    raw = data.get("items")
    if not isinstance(raw, list):
        raise RuntimeError(f"Unexpected sentence payload: {data!r}")
    seen_batch: set[str] = set()
    out: list[str] = []
    for entry in raw:
        s = str(entry).strip()
        if not s:
            continue
        key = s.lower()
        if key in seen_batch or key in seen_lower:
            continue
        seen_batch.add(key)
        out.append(s)
    return out[:count]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_existing_manifest(out_dir: Path) -> dict:
    manifest_path = out_dir / "problems.json"
    if not manifest_path.exists():
        raise RuntimeError(
            f"{manifest_path} not found; run once without --append/--reuse-sentences first."
        )
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def load_existing_sentences(out_dir: Path) -> list[str]:
    data = load_existing_manifest(out_dir)
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise RuntimeError("problems.json has no items")
    return [str(it.get("text", "")).strip() for it in items if it.get("text")]


def clear_audio_files(out_dir: Path, extensions: tuple[str, ...]) -> int:
    removed = 0
    for path in sorted(out_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in extensions:
            path.unlink()
            removed += 1
    return removed


def synth_items(
    sentences: list[str],
    start_id: int,
    elevenlabs_key: str,
    tts_model: str,
    out_dir: Path,
) -> list[dict]:
    """TTS each sentence with a rotating voice; return manifest entries.

    The rotation is keyed off the item's global id so numbering stays
    consistent across append runs.
    """
    problems: list[dict] = []
    total = len(sentences)
    for offset, sentence in enumerate(sentences):
        item_id = start_id + offset
        voice_id, voice_name, accent = VOICE_ROTATION[
            (item_id - 1) % len(VOICE_ROTATION)
        ]
        slug = f"sentence-{item_id:02d}.mp3"
        preview = sentence[:60] + ("…" if len(sentence) > 60 else "")
        print(
            f"      {offset + 1:>2}/{total}  id={item_id:<3} {voice_name:<8} "
            f"({accent:<10})  {preview}"
        )
        try:
            mp3 = elevenlabs_tts_mp3(sentence, elevenlabs_key, voice_id, tts_model)
        except Exception as exc:
            print(f"      TTS failed for {slug}: {exc}", file=sys.stderr)
            time.sleep(2)
            continue
        (out_dir / slug).write_bytes(mp3)
        problems.append(
            {
                "id": item_id,
                "text": sentence,
                "audio": slug,
                "voice": voice_name,
                "voice_id": voice_id,
                "accent": accent,
            }
        )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--out-dir", default="site/public/repeat-sentence")
    parser.add_argument("--llm-model", default=DEFAULT_LLM)
    parser.add_argument("--tts-model", default=DEFAULT_TTS_MODEL)
    parser.add_argument(
        "--reuse-sentences",
        action="store_true",
        help="Read texts from an existing problems.json and only regenerate the audio.",
    )
    parser.add_argument(
        "--append",
        type=int,
        default=0,
        metavar="N",
        help="Generate N additional items on top of the existing problems.json.",
    )
    parser.add_argument(
        "--difficulty",
        choices=sorted(DIFFICULTY_SPECS.keys()),
        default="easy",
        help="Sentence difficulty for new-generation batches (default: easy).",
    )
    args = parser.parse_args()

    openai_key = os.environ.get("OPENAI_API_KEY")
    elevenlabs_key = os.environ.get("ELEVENLABS_API_KEY")
    if not elevenlabs_key:
        print("ERROR: ELEVENLABS_API_KEY missing from .env", file=sys.stderr)
        return 1

    out_dir = (ROOT / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------------------
    # APPEND MODE — generate N more items and merge with existing.
    # --------------------------------------------------------------
    if args.append > 0:
        if not openai_key:
            print("ERROR: OPENAI_API_KEY missing from .env", file=sys.stderr)
            return 1
        existing = load_existing_manifest(out_dir)
        existing_items = existing.get("items") or []
        existing_texts = [it.get("text", "") for it in existing_items]
        next_id = max((it.get("id", 0) for it in existing_items), default=0) + 1
        print(
            f"[1/3] Appending {args.append} items (difficulty={args.difficulty}) "
            f"starting at id={next_id}. Existing count: {len(existing_items)}."
        )
        new_sentences = generate_sentences(
            args.append,
            openai_key,
            args.llm_model,
            difficulty=args.difficulty,
            already_seen=existing_texts,
        )
        print(f"      LLM returned {len(new_sentences)} fresh, non-duplicate sentences.")
        if not new_sentences:
            print("ERROR: no new sentences produced", file=sys.stderr)
            return 1
        print(f"[2/3] Voicing {len(new_sentences)} new items via ElevenLabs...")
        new_items = synth_items(
            new_sentences, next_id, elevenlabs_key, args.tts_model, out_dir
        )
        if not new_items:
            print("ERROR: no audio was produced", file=sys.stderr)
            return 1
        merged = existing_items + new_items
        manifest = existing.copy() if isinstance(existing, dict) else {}
        meta = manifest.get("meta") or {}
        meta["tts_provider"] = "elevenlabs"
        meta["tts_model"] = args.tts_model
        meta["llm_model"] = args.llm_model
        meta["voices"] = [
            {"id": v[0], "name": v[1], "accent": v[2]} for v in VOICE_ROTATION
        ]
        meta["generated_count"] = len(merged)
        manifest["meta"] = meta
        manifest["items"] = merged
        (out_dir / "problems.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            f"[3/3] Wrote {len(new_items)} new mp3s and updated problems.json "
            f"({len(merged)} total items)."
        )
        return 0

    # --------------------------------------------------------------
    # FRESH / REUSE MODE — regenerate everything (destructive).
    # --------------------------------------------------------------
    if args.reuse_sentences:
        print(f"[1/3] Reusing sentences from {out_dir.relative_to(ROOT)}/problems.json")
        sentences = load_existing_sentences(out_dir)
        print(f"      Got {len(sentences)} sentences to re-voice.")
    else:
        if not openai_key:
            print("ERROR: OPENAI_API_KEY missing from .env", file=sys.stderr)
            return 1
        print(
            f"[1/3] Generating {args.count} sentences via {args.llm_model} "
            f"(difficulty={args.difficulty})..."
        )
        sentences = generate_sentences(
            args.count,
            openai_key,
            args.llm_model,
            difficulty=args.difficulty,
        )
        print(f"      Got {len(sentences)} unique sentences.")
    if not sentences:
        print("ERROR: no sentences available", file=sys.stderr)
        return 1

    removed = clear_audio_files(out_dir, (".mp3", ".wav"))
    if removed:
        print(f"      Cleared {removed} stale audio file(s).")

    print(
        f"[2/3] Synthesising audio via ElevenLabs (model={args.tts_model}), "
        f"rotating {len(VOICE_ROTATION)} voices..."
    )
    problems = synth_items(sentences, 1, elevenlabs_key, args.tts_model, out_dir)
    if not problems:
        print("ERROR: no audio was produced", file=sys.stderr)
        return 1

    manifest = {
        "meta": {
            "tts_provider": "elevenlabs",
            "tts_model": args.tts_model,
            "llm_model": args.llm_model,
            "voices": [
                {"id": v[0], "name": v[1], "accent": v[2]} for v in VOICE_ROTATION
            ],
            "generated_count": len(problems),
        },
        "items": problems,
    }
    (out_dir / "problems.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"[3/3] Wrote {len(problems)} audio files + problems.json to "
        f"{out_dir.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
