#!/usr/bin/env python3
"""Build English-to-Russian vocabulary quiz JS files.

Two source modes:
  --pdf <path>          extract words from a book PDF and generate a quiz
  --wordlist-url <url>  fetch a pre-made word list (currently the ESL Lounge
                        CEFR pages) and generate a quiz for it

Common:
  --count N             cap on items (PDF mode) / cap on words picked (wordlist)
  --out src/js/vocab.js output JS file
  --source-id ID        id embedded in the file so the extension can distinguish
                        multiple sources
  --source-name "Name"  human-readable name shown in the popup dropdown
  --model MODEL         override the OpenAI model (default: GPT-5.6 Terra)

Backfill mode (--backfill-examples) only adds "examples" to existing items.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.6-terra"
BATCH_SIZE = 40
MAX_TEXT_CHARS = 45_000
CHUNK_SIZE = 30_000
JSON_MARKER_START = "/*__LG_JSON__*/"
JSON_MARKER_END = "/*__LG_END__*/"
HTTP_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

def extract_pdf_text(pdf_path: Path, page_range: str | None) -> str:
    reader = PdfReader(str(pdf_path))
    total = len(reader.pages)
    if page_range:
        start_str, _, end_str = page_range.partition("-")
        start = max(1, int(start_str))
        end = int(end_str) if end_str else start
        end = min(total, end)
        page_indexes = range(start - 1, end)
    else:
        page_indexes = range(total)

    chunks = []
    for i in page_indexes:
        chunks.append(reader.pages[i].extract_text() or "")
    text = "\n".join(chunks)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Domain-specific PDF cleaners
# ---------------------------------------------------------------------------

_PTE_SECTIONS = (
    "Read Aloud",
    "Repeat Sentence",
    "Describe Image",
    "Retell Lecture",
    "Answer Short Question",
    "Summarize Written Text",
    "Summarize Group Discussion",
    "Summarize Spoken Text",
    "Write Essay",
    "Reading & Writing",
    "Multiple Choice",
    "Multiple-choice",
    "Fill in the Blanks",
    "Reorder Paragraphs",
    "Reading: Fill in the Blanks",
    "Highlight Correct Summary",
    "Select Missing Word",
    "Highlight Incorrect Words",
    "Write from Dictation",
    "Personal introduction",
    "Speaking",
    "Reading",
    "Writing",
    "Listening",
)
_PTE_SECTION_RE = re.compile(
    r"^(?:" + "|".join(re.escape(s) for s in _PTE_SECTIONS) + r")"
    r"(?:\s*\([^)]*\))?(?:\s+\d+)?[:.]?\s*$",
    re.IGNORECASE,
)
_PTE_LABEL_RE = re.compile(
    r"^(Sample answer|Suggested answer|Correct answer|Correct|Incorrect|Answer|Note)\s*:.*$",
    re.IGNORECASE,
)


def clean_pte_text(raw: str) -> str:
    kept: list[str] = []
    for line in raw.split("\n"):
        stripped = line.strip()
        if not stripped:
            kept.append("")
            continue
        if "Pearson Education Limited" in stripped:
            continue
        # Bare page number (with optional trailing punctuation)
        if re.fullmatch(r"\d{1,3}[.)]?", stripped):
            continue
        if _PTE_SECTION_RE.match(stripped):
            continue
        if _PTE_LABEL_RE.match(stripped):
            continue
        kept.append(line)
    text = "\n".join(kept)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


PARSERS = {
    "plain": lambda text: text,
    "pte": clean_pte_text,
}


def chunk_text(text: str, max_chars: int = CHUNK_SIZE) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    paras = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for para in paras:
        para_len = len(para) + 2  # for the joining "\n\n"
        if current and current_len + para_len > max_chars:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = para_len
        else:
            current.append(para)
            current_len += para_len
    if current:
        chunks.append("\n\n".join(current))
    # If a single paragraph is oversized, hard-split it.
    result: list[str] = []
    for chunk in chunks:
        if len(chunk) <= max_chars:
            result.append(chunk)
            continue
        for start in range(0, len(chunk), max_chars):
            result.append(chunk[start : start + max_chars])
    return result


# ---------------------------------------------------------------------------
# ESL Lounge C1 / other CEFR list scraper
# ---------------------------------------------------------------------------

_ESL_ENTRY_RE = re.compile(r"^(?:to\s+)?([A-Za-z][A-Za-z\-']*(?:\s+[A-Za-z\-']+)*)\s*(\([^)]*\))?\s*$")


def fetch_esl_wordlist(url: str) -> list[str]:
    resp = requests.get(url, timeout=30, headers={"User-Agent": HTTP_USER_AGENT})
    resp.raise_for_status()
    html = resp.text
    # Each word-row contains td class=left / td class=right; entries split by <br>.
    cells = re.findall(
        r'<td\s+class="(?:left|right)"[^>]*>(.*?)</td>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    words: list[str] = []
    seen: set[str] = set()
    for cell in cells:
        for chunk in re.split(r"<br\s*/?>", cell, flags=re.IGNORECASE):
            plain = re.sub(r"<[^>]+>", "", chunk).strip()
            if not plain:
                continue
            # Handle "leak (n) / to leak (v)" by splitting on " / "
            for piece in re.split(r"\s*/\s*", plain):
                piece = piece.strip()
                if not piece:
                    continue
                m = _ESL_ENTRY_RE.match(piece)
                if not m:
                    continue
                word = m.group(1).strip().lower()
                if not word or word in seen:
                    continue
                seen.add(word)
                words.append(word)
    return words


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

def _item_schema_hint() -> str:
    return (
        'For each item produce:\n'
        '  - "word": the English headword, lower-cased unless proper noun.\n'
        '  - "base": the base/root of "word" — if "word" is derived from a\n'
        '    simpler English word, show that (e.g., gritty -> grit,\n'
        '    nuzzled -> nuzzle, thoughtless -> thought, judicial -> judge).\n'
        '    If "word" is already its own base, set "base" equal to "word".\n'
        '  - "correct": the best Russian translation, single form, no quotes,\n'
        '    no parenthetical.\n'
        '  - "wrong": array of exactly 3 Russian distractors that look plausible\n'
        '    (same part of speech, related field) but are clearly wrong to a\n'
        '    native Russian speaker. Distractors must NOT be synonyms of "correct".\n'
        '  - "examples": exactly 3 short natural English sentences (8-16 words)\n'
        '    using "word" in different contexts, self-contained, showing meaning\n'
        '    by context (not a dictionary definition).\n'
    )


def build_pdf_prompt(text: str, count: int, seen_words: list[str]) -> list[dict]:
    seen_hint = (
        "\n\nDo NOT reuse any of these already-generated headwords: "
        + ", ".join(sorted(set(seen_words)))
        if seen_words
        else ""
    )
    system = (
        "You build English-to-Russian vocabulary quizzes for an advanced learner "
        "based on a passage they are reading. You return STRICT JSON only, no prose."
    )
    user = (
        f"Below is text from the book the learner is reading.\n"
        f"Pull out {count} vocabulary items worth learning. Prefer:\n"
        f"  - moderately advanced single words (verbs, adjectives, nouns)\n"
        f"  - short idiomatic phrases or two-word collocations from the text\n"
        f"  - occasional rare/period words\n"
        f"Skip trivially common words (the, was, house, etc.).\n\n"
        f"Use the exact sense each item has in this passage. The Russian "
        f"translation and all examples must teach that contextual sense, not a "
        f"different dictionary meaning of the same spelling.\n\n"
        f"{_item_schema_hint()}\n"
        f'Return a JSON object of shape:\n'
        f'{{"items": [{{"word":"...","base":"...","correct":"...",'
        f'"wrong":["...","...","..."],"examples":["...","...","..."]}}]}}\n\n'
        f"Exactly {count} items. No duplicates. No commentary.{seen_hint}\n\n"
        f"--- PASSAGE START ---\n{text[:MAX_TEXT_CHARS]}\n--- PASSAGE END ---\n"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_wordlist_prompt(words: list[str]) -> list[dict]:
    listing = "\n".join(f"- {w}" for w in words)
    system = (
        "You enrich English vocabulary lists with Russian translations, plausible "
        "distractors, base forms and English usage examples for an advanced learner. "
        "You return STRICT JSON only, no prose."
    )
    user = (
        f"You are given a list of English headwords. Produce a quiz entry for "
        f"EACH one, in the same order.\n\n"
        f"{_item_schema_hint()}\n"
        f'Return a JSON object of shape:\n'
        f'{{"items": [{{"word":"...","base":"...","correct":"...",'
        f'"wrong":["...","...","..."],"examples":["...","...","..."]}}]}}\n\n'
        f"Headwords (one per line):\n{listing}\n"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_examples_prompt(words: list[dict]) -> list[dict]:
    system = (
        "You add English usage examples to vocabulary entries. "
        "You return STRICT JSON only, no prose."
    )
    listing = "\n".join(f'- "{w["word"]}" (means: {w["correct"]})' for w in words)
    user = (
        "For each headword below, produce exactly 3 short natural English sentences\n"
        "using the headword. Sentences must be 8-16 words, self-contained, and show\n"
        "meaning by context (not a dictionary definition). Vary contexts.\n\n"
        f"Headwords:\n{listing}\n\n"
        'Return a JSON object of shape:\n'
        '{"items": [{"word": "...", "examples": ["...", "...", "..."]}]}\n\n'
        "One entry per headword, same spelling. No commentary.\n"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

def _extract_json(content: str) -> dict:
    text = content.strip()
    # Some models (Claude on Bedrock) wrap JSON in ```json ... ``` regardless of
    # response_format. Strip common fence variants first.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```\s*$", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    # If there's still leading prose, extract the first {...} block.
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


def call_openai(messages: list[dict], api_key: str, model: str) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "input": messages,
        "reasoning": {"effort": "low"},
        "text": {"format": {"type": "json_object"}},
        "max_output_tokens": 12_000,
        "store": False,
    }
    resp = requests.post(
        OPENAI_RESPONSES_URL, headers=headers, json=body, timeout=240
    )
    if resp.status_code != 200:
        raise RuntimeError(f"OpenAI error {resp.status_code}: {resp.text[:500]}")
    payload = resp.json()
    return _extract_json(_response_text(payload))


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def normalize_examples(raw) -> list:
    if not isinstance(raw, list):
        return []
    cleaned = [str(s).strip() for s in raw if str(s).strip()]
    return cleaned[:3]


def normalize_item(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    word = str(item.get("word", "")).strip()
    correct = str(item.get("correct", "")).strip()
    wrong = item.get("wrong") or []
    if not word or not correct or not isinstance(wrong, list):
        return None
    wrong = [str(w).strip() for w in wrong if str(w).strip()]
    if len(wrong) < 3:
        return None
    entry: dict = {"word": word, "correct": correct, "wrong": wrong[:3]}
    base = str(item.get("base", "")).strip()
    if base:
        entry["base"] = base
    examples = normalize_examples(item.get("examples"))
    if examples:
        entry["examples"] = examples
    return entry


# ---------------------------------------------------------------------------
# Vocab file read/write with source metadata
# ---------------------------------------------------------------------------

def read_existing_vocab(js_path: Path) -> tuple[dict, list[dict]]:
    """Return (meta_dict, items_list) from a previously-written vocab file."""
    if not js_path.exists():
        return {"id": "", "name": ""}, []
    text = js_path.read_text(encoding="utf-8")

    marker_re = re.escape(JSON_MARKER_START) + r"(.*?)" + re.escape(JSON_MARKER_END)
    match = re.search(marker_re, text, re.DOTALL)
    if match:
        payload = json.loads(match.group(1))
        return payload.get("meta") or {}, payload.get("items") or []

    # Fallback: legacy format with `const LITERATEGOGGLES_VOCAB = [...];`
    legacy = re.search(
        r"const\s+LITERATEGOGGLES_VOCAB\s*=\s*(\[.*?\])\s*;",
        text,
        re.DOTALL,
    )
    if not legacy:
        raise RuntimeError(f"Could not parse vocab data from {js_path}")
    items = json.loads(legacy.group(1))
    return {"id": "", "name": ""}, items


def write_vocab_js(meta: dict, items: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"meta": meta, "items": items}
    json_blob = json.dumps(payload, ensure_ascii=False, indent=2)
    contents = (
        "// AUTO-GENERATED by scripts/vocab_builder.py. Do not edit by hand.\n"
        f"// Source: {meta.get('id', '?')} · {meta.get('name', '')}\n"
        f"// Items: {len(items)}\n"
        "(function () {\n"
        f"  const payload = {JSON_MARKER_START}{json_blob}{JSON_MARKER_END};\n"
        "  if (typeof globalThis === 'undefined') return;\n"
        "  if (!globalThis.LiterateGoggles) globalThis.LiterateGoggles = {};\n"
        "  if (!Array.isArray(globalThis.LiterateGoggles.vocabSources)) {\n"
        "    globalThis.LiterateGoggles.vocabSources = [];\n"
        "  }\n"
        "  const source = { ...payload.meta, items: payload.items };\n"
        "  const list = globalThis.LiterateGoggles.vocabSources;\n"
        "  const idx = list.findIndex((s) => s.id === source.id);\n"
        "  if (idx >= 0) list[idx] = source; else list.push(source);\n"
        "  if (!globalThis.LiterateGoggles.vocab) globalThis.LiterateGoggles.vocab = source.items;\n"
        "})();\n"
    )
    out_path.write_text(contents, encoding="utf-8")


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------

def backfill_examples(
    js_path: Path,
    api_key: str,
    model: str,
    batch_size: int = 20,
) -> int:
    meta, items = read_existing_vocab(js_path)
    todo = [it for it in items if not it.get("examples")]
    if not todo:
        print("      Nothing to backfill; every item already has examples.")
        write_vocab_js(meta or {"id": "", "name": ""}, items, js_path)
        return 0

    by_word = {it["word"].lower(): it for it in items}
    updated = 0
    for start in range(0, len(todo), batch_size):
        batch = todo[start : start + batch_size]
        print(
            f"      backfill batch {start // batch_size + 1}: "
            f"asking for examples on {len(batch)} words..."
        )
        try:
            data = call_openai(build_examples_prompt(batch), api_key, model)
        except Exception as exc:
            print(f"      batch failed: {exc}", file=sys.stderr)
            continue
        raw_items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(raw_items, list):
            print("      batch returned unexpected shape; skipping", file=sys.stderr)
            continue
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            word = str(raw.get("word", "")).strip().lower()
            examples = normalize_examples(raw.get("examples"))
            entry = by_word.get(word)
            if entry and examples:
                entry["examples"] = examples
                updated += 1
        print(f"      running total: {updated} / {len(todo)} examples added")

    write_vocab_js(meta or {"id": "", "name": ""}, items, js_path)
    return updated


# ---------------------------------------------------------------------------
# Generation loops
# ---------------------------------------------------------------------------

def _consume_batch(
    raw_items,
    items: list[dict],
    seen: set[str],
    target: int | None,
) -> int:
    added = 0
    if not isinstance(raw_items, list):
        return 0
    for raw in raw_items:
        item = normalize_item(raw)
        if not item:
            continue
        key = item["word"].lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
        added += 1
        if target is not None and len(items) >= target:
            break
    return added


def generate_from_pdf(
    chunks: list[str],
    count: int,
    api_key: str,
    model: str,
) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    if not chunks:
        return items
    n_chunks = len(chunks)
    per_chunk = max(1, (count + n_chunks - 1) // n_chunks)
    for chunk_idx, chunk in enumerate(chunks):
        remaining_total = count - len(items)
        if remaining_total <= 0:
            break
        chunk_target = min(per_chunk, remaining_total)
        # Give the last chunk a chance to fill any shortfall from earlier chunks.
        if chunk_idx == n_chunks - 1:
            chunk_target = remaining_total
        print(
            f"  chunk {chunk_idx + 1}/{n_chunks} ({len(chunk)} chars): "
            f"aiming for {chunk_target} items"
        )
        chunk_added_total = 0
        remaining_chunk = chunk_target
        batch_num = 0
        while remaining_chunk > 0:
            batch_num += 1
            want = min(BATCH_SIZE, remaining_chunk)
            print(f"      batch {batch_num}: asking for {want} items...")
            try:
                data = call_openai(
                    build_pdf_prompt(chunk, want, sorted(seen)), api_key, model
                )
            except Exception as exc:
                print(f"      batch {batch_num} failed: {exc}", file=sys.stderr)
                time.sleep(2)
                continue
            added = _consume_batch(data.get("items"), items, seen, count)
            chunk_added_total += added
            print(
                f"      batch {batch_num}: kept {added} new items "
                f"(chunk {chunk_added_total}/{chunk_target}, "
                f"total {len(items)}/{count})"
            )
            remaining_chunk = chunk_target - chunk_added_total
            remaining_total = count - len(items)
            if remaining_total <= 0:
                break
            if added == 0:
                print("      no new items from this chunk; moving on")
                break
    return items


def generate_from_wordlist(
    words: list[str],
    api_key: str,
    model: str,
    batch_size: int = 25,
) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for start in range(0, len(words), batch_size):
        batch = words[start : start + batch_size]
        batch_num = start // batch_size + 1
        total_batches = (len(words) + batch_size - 1) // batch_size
        print(
            f"      batch {batch_num}/{total_batches}: enriching "
            f"{len(batch)} words..."
        )
        try:
            data = call_openai(build_wordlist_prompt(batch), api_key, model)
        except Exception as exc:
            print(f"      batch {batch_num} failed: {exc}", file=sys.stderr)
            time.sleep(2)
            continue
        added = _consume_batch(data.get("items"), items, seen, None)
        print(
            f"      batch {batch_num}: kept {added} items "
            f"(total {len(items)}/{len(words)})"
        )
    return items


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", help="Path to source PDF")
    parser.add_argument("--wordlist-url", help="URL to fetch a pre-made word list from")
    parser.add_argument("--out", default="src/js/vocab.js", help="Output JS file")
    parser.add_argument("--count", type=int, default=100, help="Total items (PDF mode) or word cap (wordlist mode)")
    parser.add_argument("--pages", default=None, help="1-indexed page range like '1-24' (PDF mode)")
    parser.add_argument(
        "--parser",
        choices=sorted(PARSERS.keys()),
        default="plain",
        help="Domain-specific PDF cleaner to apply before chunking (default: plain)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=CHUNK_SIZE,
        help=f"Max chars per chunk sent to the LLM (default: {CHUNK_SIZE})",
    )
    parser.add_argument("--source-id", default=None, help="ID to embed in the file (e.g., 'orwell1984')")
    parser.add_argument("--source-name", default=None, help="Display name (e.g., '1984 (chapters 1-2)')")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--backfill-examples",
        action="store_true",
        help="Skip generation; only add examples to items in --out that lack them.",
    )
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY missing from .env", file=sys.stderr)
        return 1

    out_path = (ROOT / args.out).resolve()

    if args.backfill_examples:
        print(f"[backfill] Adding examples to items in {out_path.relative_to(ROOT)}...")
        added = backfill_examples(out_path, api_key, args.model)
        print(f"Done. Added examples to {added} items.")
        return 0

    if not args.pdf and not args.wordlist_url:
        print(
            "ERROR: either --pdf, --wordlist-url or --backfill-examples is required",
            file=sys.stderr,
        )
        return 1
    if args.pdf and args.wordlist_url:
        print("ERROR: pass either --pdf or --wordlist-url, not both", file=sys.stderr)
        return 1

    if not args.source_id:
        print("ERROR: --source-id is required when generating a new file", file=sys.stderr)
        return 1
    source_name = args.source_name or args.source_id
    meta = {"id": args.source_id, "name": source_name}

    if args.pdf:
        pdf_path = Path(os.path.expanduser(args.pdf)).resolve()
        if not pdf_path.exists():
            print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
            return 1
        print(f"[1/3] Extracting text from {pdf_path.name}...")
        raw_text = extract_pdf_text(pdf_path, args.pages)
        print(f"      Raw: {len(raw_text)} chars.")
        cleaner = PARSERS[args.parser]
        text = cleaner(raw_text)
        if args.parser != "plain":
            print(f"      After --parser {args.parser}: {len(text)} chars.")
        if not text:
            print("ERROR: no text extracted", file=sys.stderr)
            return 1
        chunks = chunk_text(text, args.chunk_size)
        print(
            f"[2/3] Requesting {args.count} quiz items from {args.model} "
            f"across {len(chunks)} chunk(s), batches of {BATCH_SIZE}..."
        )
        items = generate_from_pdf(chunks, args.count, api_key, args.model)
    else:
        print(f"[1/3] Fetching word list: {args.wordlist_url}")
        words = fetch_esl_wordlist(args.wordlist_url)
        print(f"      Parsed {len(words)} unique words.")
        if args.count and len(words) > args.count:
            words = words[: args.count]
            print(f"      Capped to first {len(words)} (via --count).")
        if not words:
            print("ERROR: no words parsed from URL", file=sys.stderr)
            return 1
        print(f"[2/3] Enriching {len(words)} words via {args.model}...")
        items = generate_from_wordlist(words, api_key, args.model)

    print(f"[3/3] Writing {len(items)} items to {out_path.relative_to(ROOT)}")
    write_vocab_js(meta, items, out_path)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
