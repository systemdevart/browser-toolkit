# LiterateGoggles

LiterateGoggles is a personal browser toolkit for tweaking the way websites look and behave. It starts with small conveniences—like hiding LeetCode difficulty badges so you can focus on solving the problem—and invites you to grow a collection of similar experiments for any site you use.

## daily.chebakov.me

The repository also contains a personal morning dashboard built with a static
Next.js/React frontend and a FastAPI backend. The dashboard and its sandbox
IELTS routes are protected by Google OpenID Connect and a single verified-email
allowlist; OAuth tokens and application sessions remain server-side or in
secure `HttpOnly` cookies.

The homepage follows [DAILY.md](./DAILY.md) and combines:

- direct access to English vocabulary and a 1,000-word French A1 quiz on
  `daily.chebakov.me`, plus speaking and writing practice hosted exclusively on
  `sandbox.chebakov.me`, with audio-only speaking prompts read by random
  British ElevenLabs voices;
- a preserved but currently hidden repertoire-recall feature with five drills
  from recent Chess.com games and five deeper theory drills;
- bilingual "on this day" history from English and Russian Wikipedia;
- three Russian and three English sayings sampled at daily creation from the
  full Wikiquote collections, with OpenAI-generated translation, meaning, and
  usage notes;
- daily ML research selected from Hugging Face Papers, the Hugging Face blog,
  and alphaXiv;
- 27 daily source-grounded mathematics and ML problems, with worked solutions
  and transfer exercises. Opening a worked solution is saved, while unopened
  problems carry into the next daily set;
- server-enforced 25-minute English- and Russian-reading timers, with a
  completion chime and durable SQLite history for future statistics;
- a SQLite-backed active-recall queue for concepts learned during the day,
  using Russian OpenAI-generated indirect questions that change on each due date,
  1, 3, 7, 14, 30, 60, and 120-day review gaps, next-day retries after misses,
  and automatic archival after full mastery;
- random-depth, multiple-choice chess opening-name identification from
  Lichess's CC0 opening dataset, with automatic scoring, repeatable positions,
  optional movable-board continuation bonuses, and local progress;
- short introductions to important car models;
- public-domain Russian poetry for memory practice.

FastAPI refreshes the digest at midnight in the configured timezone, with a
first-visit fallback after a date change. The generated digest and selection
history persist in `api/daily.json`, preventing research, sayings, cars, and
poetry from repeating across restarts. The chess book is checked in at
`api/chess_repertoire.json`; daily chess state and non-repetition history live
in `api/chess_drills.json`. All LLM generation uses
OpenAI GPT-5.6 Terra through the Responses API; the problem studio keeps
GPT-5.6 Sol with high reasoning effort and its own non-repetition history in
`api/math_daily.json`. Provider credentials remain server-side.

Successfully evaluated IELTS writing attempts are saved in
`api/ielts_writing.sqlite3`, including the original response, timing, criterion
scores, feedback, and a minimal-change band-7.5 rewrite. This durable structure
is ready for future progress charts without exposing essay history publicly.
Concepts and their complete recall history are stored separately in
`api/concept_memory.sqlite3`.

The French beginner ranking and simple pronunciation spellings are adapted
from the [Vocabcraft French A1 deck](https://vocabcraft.com/decks/french),
licensed under CC BY-SA 4.0. Russian meanings, distractors, and short examples
are generated with GPT-5.6 Terra; pronunciation playback uses the browser's
standard French voice.

See [api/README.md](./api/README.md) for local and production setup.

## What it can do today

- Strip rank/file coordinate overlays from Aimchess chessboards when you'd rather rely on intuition.
- Hide LeetCode problem difficulty labels until you want to see them.
- Block Chess.com with a full-screen reminder once you've already played more than three games in a day.
- Keep a global on/off switch so you can pause every tweak with a single click.
- Offer a simple registry (`src/js/features.js`) where new ideas can be added without touching the rest of the codebase.

## Install from source

1. Clone this repository.
2. Install dependencies: `npm install`.
3. Build the extension: `npm run build`.
4. Open Chrome (or any Chromium-based browser) and navigate to `chrome://extensions/`.
5. Enable **Developer mode**.
6. Click **Load unpacked** and pick the `dist` folder from this project.

## Development workflow

- Build once: `npm run build`
- Build and watch for changes: `npm run watch`
- Package a zip for distribution: `npm run zip`

## Adding your own tweaks

1. Open `src/js/features.js`.
2. Add a new entry to `LITERATEGOGGLES_FEATURES` with:
   - a unique `id`,
   - a `name` and `description` for the popup,
   - a `storageKey` to remember the toggle state,
   - an `appliesTo(location)` function to limit where it runs,
   - `onEnable`/`onDisable` hooks to apply your changes.
3. Update `src/css` or `src/js` to include any styles or scripts your feature needs.
4. Run `npm run build` (or `npm run watch`) and reload the unpacked extension.

Each feature appears as its own toggle in the popup so you can experiment freely without disturbing the rest of your stack.

## License

MIT
