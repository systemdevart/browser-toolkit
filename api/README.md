# Daily and sandbox FastAPI backend

One Python service backs the static Next.js site. It prepares and remembers the
daily morning digest, keeps the shared vocab bans API, and runs the server-only
IELTS pipelines proxied by `sandbox.chebakov.me`.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/auth/login` | Start Google OpenID Connect with state, nonce, and PKCE |
| `GET` | `/auth/callback/` | Verify Google identity and issue the private-site session |
| `GET` | `/auth/check` | Validate the signed session for nginx `auth_request` |
| `GET` | `/auth/logout` | Clear the shared daily/sandbox session |
| `GET` | `/api/health` | Service and provider-key readiness |
| `GET` | `/api/daily` | Return today's cached digest, generating it when stale |
| `GET` | `/api/daily/math` | Return 27 daily source-grounded problems and solutions |
| `POST` | `/api/daily/math/problems/{problemId}/solution-opened` | Save that a worked solution was opened |
| `GET` | `/api/daily/chess` | Return five repertoire-matched game positions and five theory positions |
| `GET` | `/api/daily/opening-names` | Sample a named Lichess opening position and optional book continuation |
| `GET` | `/api/daily/timers` | Return today's focus timers and accumulated totals |
| `POST` | `/api/daily/timers/{activityKey}/start` | Irreversibly start today's 25-minute activity |
| `GET` | `/api/daily/concepts` | Return due and upcoming active-recall concepts |
| `POST` | `/api/daily/concepts` | Save a concept and schedule its first recall |
| `POST` | `/api/daily/concepts/{conceptId}/reviews` | Save a remembered/not-yet result and reschedule it |
| `DELETE` | `/api/daily/concepts/{conceptId}` | Remove an active concept and its recall history |
| `GET` | `/api/vocab/bans` | Fetch all shared vocab bans |
| `POST` | `/api/vocab/bans/<sourceId>` | Ban `{ "word": … }` |
| `DELETE` | `/api/vocab/bans/<sourceId>` | Clear one source |
| `DELETE` | `/api/vocab/bans/<sourceId>/<word>` | Unban one word |
| `POST` | `/api/ielts/topic` | Generate a Speaking Part 1, 2, or 3 topic with GPT-5.6 Terra |
| `POST` | `/api/ielts/topic/audio` | Read a speaking topic with a random British ElevenLabs voice |
| `POST` | `/api/ielts/transcribe` | Transcribe audio and assess audible delivery with OpenAI |
| `POST` | `/api/ielts/evaluate` | Combine transcript and audio evidence into band-7.5 feedback |
| `POST` | `/api/ielts/writing/topic` | Generate Academic visuals, General Training letters, or Task 2 essays |
| `POST` | `/api/ielts/writing/evaluate` | Evaluate, minimally rewrite for band 7.5, and save the completed attempt |

Speaking prompts are never rendered as text. The backend selects a random
British voice available to the ElevenLabs account and synthesizes the complete
question with `eleven_multilingual_v2`. The browser plays it once, then starts
microphone recording and the answer timer together when playback ends. It
converts the completed recording to 16 kHz mono WAV, then calls
transcription/audio assessment and final evaluation separately so it can show
the real pipeline stage and retry evaluation without uploading audio again.
Recordings are not persisted by the backend. GPT-4o Transcribe produces the
text, GPT-Audio-1.5 listens for pronunciation, rhythm, intelligibility, and
naturalness, and GPT-5.6 Terra produces structured IELTS feedback plus a complete
band-7.5 response rewritten with the smallest necessary changes.
Provider-backed routes have a small per-IP, in-memory hourly limit as a second
cost ceiling behind the private-site authentication layer.

Google sign-in uses the server-side authorization-code flow with a signed
anti-CSRF state value, PKCE, an OpenID Connect nonce, and cryptographic ID-token
validation. Only the configured verified email is accepted. The resulting
30-day HMAC-signed session is stored in a `Secure`, `HttpOnly`, `SameSite=Lax`
cookie scoped to `.chebakov.me`, allowing nginx to protect both the daily site
and its sandbox IELTS routes without exposing Google tokens to JavaScript.

Concept memory uses active retrieval rather than passive rereading. A new
concept is first due tomorrow. On each due date, a bounded background worker
uses GPT-5.6 Terra to generate one new indirect identification question without
blocking concept reads or saves. The question is checked for direct target-name
leakage and Russian-language output before it reaches the page. Every question
is Russian even when the concept comes from another language. Prior questions
are supplied to the model to prevent repetition; given names and surnames use
etymological clues. Successful recalls then use gaps of 3, 7, 14, 30, 60, and 120 days. A
missed recall keeps the current stage and returns the concept tomorrow. The last
successful recall marks the concept completed and removes it from the active
queue while preserving completion and review history for statistics.

Opening-name practice downloads and caches the official Lichess
`chess-openings` `a.tsv` through `e.tsv` source files. Only exact named
positions are sampled, so a deeper variation is never shown before its defining
moves have occurred. Sampling is balanced across shallow, medium, and deep
positions. Each response includes the exact name and plausible randomized
alternatives for automatic multiple-choice scoring; correct positions remain in
the sampling pool. When child lines exist, some drills also accept every
represented next book move on the interactive board.

Every successful writing evaluation is durably stored in
`api/ielts_writing.sqlite3`. Each row contains the complete task, original
response, elapsed time, word count, four criterion bands, full structured
feedback, and the minimally changed band-7.5 rewrite. Retry requests for the
same topic and unchanged response update the same deterministic attempt rather
than creating duplicates. Essay contents are not exposed through a public
history endpoint; the stored structured fields are ready for a future private
progress view.

The daily digest fetches both Wikipedia date pages, Hugging Face Daily Papers,
the Hugging Face blog, and alphaXiv. GPT-5.6 Terra selects and writes
self-contained summaries. Free car images are resolved separately through
Wikipedia's PageImages API, so the model never supplies image URLs. The result
and persistent non-repetition history are stored in `api/daily.json`. A
background scheduler refreshes after midnight in `DAILY_TIMEZONE`; the first
request after a date change is a synchronous fallback if the scheduled refresh
has not finished.

The same digest fetches the complete "Русские пословицы" and alphabetical
"English proverbs" Wikiquote pages at daily creation time, extracts their
top-level proverb entries, and samples three unseen entries from each large
pool. GPT-5.6 Terra then adds an opposite-language translation, a concise
meaning, and a careful origin or usage note. Source wording and identifiers
remain server-controlled, so the model cannot replace the sampled proverb.
Selection history is stored alongside the digest in `api/daily.json`.

The math studio reads the ten-source catalog in `api/math_sources.json`.
Complete author-hosted books and readers are downloaded and converted into
local text indexes before generation. The commercial Machine Learning System
Design book is not copied: its publisher page and the authors' complete
MIT-licensed companion repository are used instead. Refresh the local source
library with:

```sh
cd api
../.venv/bin/python scripts/download_math_sources.py
```

GPT-5.6 Sol uses high reasoning effort to prepare exactly three source-based
problems per subject: warm-up, core, and stretch. It preserves the selected
exercise's task and attribution, retaining source wording only when reuse terms
permit it. Each includes a hint, a worked solution, and a modified follow-up
with its own solution.

Mathematical analysis uses one problem per day from each requested source:
Zorich's "Математический анализ" (МЦНМО, 2021), Demidovich's "Сборник задач и
упражнений по математическому анализу" (Лань, 2022), and Kaczor and Nowak's
"Problems in Mathematical Analysis" (AMS, 2000). Complete university-hosted
texts are indexed for Zorich and the substantively identical 2021 edition of
Demidovich's 2022 sterile reprint. Kaczor and Nowak is indexed from official
publisher-controlled preview material because no unrestricted legal full
download is available.

The saved daily set, non-repetition keys, and per-problem solution-open state
live in `api/math_daily.json`. Opening the main worked solution counts the
problem as solved. At the next refresh, each unopened problem is retained at
the same difficulty; only solved slots receive new problems. If a midnight
refresh is still running, the API serves the previous set until the new one is
ready.

The chess drill service validates the checked-in book at
`api/chess_repertoire.json`, reads Chess.com's public monthly archives
serially, collects the latest 100 standard games, and parses their PGNs with
`python-chess`. It returns five early game positions whose exact board states
occur in the repertoire, plus five deeper theory positions balanced across
White and Black. The sampler rotates unseen positions and opening families.
Its daily cache and least-recently-used history live in
`api/chess_drills.json`.

Move legality and optional Stockfish 18 comparison run locally in the browser.
Correctness comes from every accepted move in the repertoire book, so a sound
book move is not rejected just because the engine ranks another move first.
The build
copies the recommended lite single-threaded Stockfish.js WebAssembly assets
from the npm package, including its GPLv3 license. No Chess.com credentials are
required because the game archive is public. Add `?refresh=true` to the chess
endpoint to pull newer games and rotate the current set manually.

Daily focus sessions are stored in SQLite at `api/daily_timers.sqlite3` by
default. SQLite is built into Python, so no separate database daemon or package
is required. The API owns the start and end timestamps: reloading or closing
the page cannot pause a running timer. The schema keeps activity, local date,
duration, start, scheduled end, and completion timestamps for later totals,
streaks, and calendar statistics. Only one focus timer may run at once, and
each activity can be completed once per local day.

## Setup

From the repository root:

```sh
python3 -m venv .venv
.venv/bin/pip install -r scripts/requirements.txt -r api/requirements.txt
```

The repository-root `.env` is loaded by both the app and systemd unit:

```dotenv
OPENAI_API_KEY=...
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_OAUTH_REDIRECT_URI=https://daily.chebakov.me/auth/callback/
AUTH_ALLOWED_EMAIL=you@example.com
AUTH_SESSION_SECRET=<at-least-32-random-characters>

# Optional overrides
OPENAI_TEXT_MODEL=gpt-5.6-terra
OPENAI_MATH_MODEL=gpt-5.6-sol
OPENAI_TEXT_REASONING_EFFORT=low
OPENAI_TRANSCRIPTION_MODEL=gpt-4o-transcribe
OPENAI_AUDIO_MODEL=gpt-audio-1.5
ELEVENLABS_API_KEY=
ELEVENLABS_TTS_MODEL=eleven_multilingual_v2
DAILY_TIMEZONE=UTC
DAILY_TIMERS_DB_FILE=api/daily_timers.sqlite3
CONCEPT_MEMORY_DB_FILE=api/concept_memory.sqlite3
IELTS_WRITING_DB_FILE=api/ielts_writing.sqlite3
CHESS_COM_USERNAME=unlimited_bezdarnost
CHESS_REPERTOIRE_FILE=api/chess_repertoire.json
CHESS_OPENING_NAMES_CACHE_FILE=api/chess_opening_names.json
```

A repository-root `.env` supplies the server-only OpenAI key without exposing
it to the statically exported site. `CREDENTIALS_ENV_FILE` remains supported
for a separately managed credential file.

For local development:

```sh
cd api
../.venv/bin/uvicorn main:app --host 127.0.0.1 --port 3011 --reload
```

## Production

The systemd unit remains named `daily-vocab-bans.service` for a no-downtime
migration from the former Node service, but now launches FastAPI:

```sh
cd ~/Projects/dotfiles
sudo make services
sudo make nginx

sudo systemctl status daily-vocab-bans
sudo journalctl -u daily-vocab-bans -f
```

Runtime bans remain in `api/bans.json`; the daily digest lives in
`api/daily.json`; the math set lives in `api/math_daily.json`; and chess drill
state lives in `api/chess_drills.json`. Timer history lives in
`api/daily_timers.sqlite3`; completed writing attempts live in
`api/ielts_writing.sqlite3`; concept recall state and history live in
`api/concept_memory.sqlite3`. All runtime files are excluded from git.
