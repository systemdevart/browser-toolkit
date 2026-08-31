# Daily

`daily.chebakov.me` supports my morning study routine. This file is the short
source of truth for the features I want on the site.

## General behaviour

- Keep the daily dashboard and its sandbox IELTS tools private behind Google
  sign-in. Allow only the configured personal Google account.
- Refresh daily content at 00:00 in the configured site timezone, or on the
  first startup or visit after the date changes.
- Keep persistent history across restarts and avoid previously shown items.
  "On this day" content may naturally repeat each year.
- Make every block self-contained: include the useful content directly and
  treat external links as optional references.
- Prefer a few relevant, high-quality items over long feeds.

## IELTS

Keep the IELTS vocabulary, speaking, and writing tools. They are an important
part of the routine and should remain focused on practical progress. Keep
vocabulary on `daily.chebakov.me`; link speaking and writing from the dashboard
but host both tools only on `sandbox.chebakov.me`. Save every successfully
evaluated writing response, its task, timing, criterion bands, and full feedback
in durable history. End writing feedback with a band-7.5 rewrite that preserves
my ideas and structure and changes only what is needed. Keep speaking prompts
hidden as text: ElevenLabs should read each prompt once with a random British
voice, then microphone recording and the answer timer should start together as
soon as playback ends. In speaking feedback, show the full transcript followed
by a complete band-7.5 version that preserves my ideas and wording and makes
only the smallest necessary changes.

## Vocabulary

Keep the existing English vocabulary pools and a separate French A1 pool with
the 1,000 most basic words, Russian answer choices, a simple pronunciation hint,
and standard French browser speech. Preserve source attribution for imported
word lists.

## Daily focus timers

Keep separate 25-minute timers for reading English books and Russian books.
Once started, a timer cannot be paused or reset and must run to completion,
then play a chime. Preserve every session in durable storage so future pages
can show totals, streaks, and other statistics. Allow only one focus timer to
run at a time and only one completion per activity per day.

## Concept recall

Keep concept creation collapsed by default. Let me save only a target concept.
On every due date, use the advanced OpenAI model to create a new self-contained
identification question without writing the concept, an inflection, or an
obvious spelling clue. Write every question in Russian, regardless of the
concept's language or origin. For given names and surnames, ask through etymology.
Persist that day's question, require an answer before revealing the concept,
and never reuse an earlier question. Use successful-recall gaps of 1, 3, 7, 14,
30, 60, and 120 days; a failed recall repeats the same step tomorrow. After the
final successful recall, remove the concept from the active queue and retain it
only as fully remembered history.

## Chess drills

Keep this repertoire-recall block hidden from the daily page until I ask to
restore it. Preserve its implementation and stored progress for later work.

Pull the latest 100 standard games for `unlimited_bezdarnost` from Chess.com
and prepare ten repertoire-recall positions every day: five matched positions
from those games and five deeper positions from opening theory.

- For White, practise the Italian Game Classical Center Attack; the Knights
  Attack/Polerio line with the Be2 retreat after `...Na5`, `...c6`, and
  `...bxc6`; the French Advance with c3 and Bd3 after the
  `...Nc6`/`...Qb6` setup; the Caro-Kann Advance with immediate c4 after
  `...Bf5`, `Nf3`, `...e6`, `Be2`, `...c5`; and the g3/Bg2 fianchetto against
  the Sicilian Najdorf.
- For Black, practise the Sicilian Accelerated Dragon, including anti-Sicilian
  sidelines such as early h3, c4, c3, Bc4, and closed setups; play the Slav
  Defense against 1.d4 and c4.
- Keep game positions between moves 3 and 9. Theory positions may go
  substantially deeper.
- Let me move pieces on a real board and give me three wrong legal tries.
  Illegal moves should not consume a try.
- Grade against the repertoire book and accept every saved book continuation,
  even when Stockfish ranks another move first. Use Stockfish to explain and
  compare moves, not as the single answer key.
- After completion, show the accepted continuation, engine comparisons, and,
  for a game sample, the move I played and the source game.
- Remember prior positions and rotate across both colours and opening families.

## Chess opening names

Sample real named positions at varied depths from the CC0 Lichess
`chess-openings` dataset. Show the board before the move sequence and make me
choose the opening family and variation from plausible alternatives, then mark
the answer automatically. After revealing the answer, sometimes ask me to play
any known book continuation on the movable board. Keep every opening in the
random pool after a correct answer and retain local correct/attempt statistics.

## On this day

Use the current date to read both the Russian and English Wikipedia date pages,
for example:

- `https://ru.wikipedia.org/wiki/24_июля`
- `https://en.wikipedia.org/wiki/July_24`

Present a concise selection of interesting historical events, holidays, and
people born on that date. Use both languages and include enough context to be
useful without opening Wikipedia.

## Sayings and catchphrases

Show three Russian and three English sayings every day. Mix recognisable
sayings with useful traditional proverbs. At daily creation time, fetch the
full Russian and English Wikiquote proverb collections and sample three unseen
entries from each language; do not build the pool around any example book,
film, or author. Use the advanced OpenAI text model to add a translation into
the other language, a short meaning, and a careful origin or usage note.
Keep the cards understandable without opening the source links and remember
selected entries so the large pools rotate without repetition.

## ML research

Review the day's notable papers and posts from:

- `https://huggingface.co/papers/`
- `https://huggingface.co/blog`
- `https://www.alphaxiv.org/`

Select work relevant to NLP, generative models, and image generation. Summarise
the problem, the main idea, important results, and why the work matters. Avoid
repeating previously covered research.

## Math and ML problem studio

Prepare three source-based problems every day for each scheduled subject:
mathematical analysis, linear algebra, Leningrad mathematical circles, deep
learning foundations, statistical learning, pen-and-paper ML, ML system
design, ML mathematics, and proof practice.

- Ground each set in a complete legitimate book or author-provided source
  cached by the backend. For a commercial book without a legal full download,
  use its official public material and complete author companion repository.
- For mathematical analysis, prepare exactly one problem from each of these
  sources every day:
  - В. А. Зорич, "Математический анализ", МЦНМО, 2021.
  - Б. П. Демидович, "Сборник задач и упражнений по математическому анализу",
    Лань, 2022.
  - W. J. Kaczor and M. T. Nowak, "Problems in Mathematical Analysis",
    AMS, 2000.
- Preserve each selected exercise's task, data, constraints, and attribution.
  Keep the source wording when its reuse terms allow it; otherwise use a
  minimal faithful restatement.
- Use OpenAI GPT-5.6 Sol with high reasoning effort to create and check a
  warm-up, core, and stretch problem.
- Show a hint, an educational worked solution, and a modified follow-up with
  its own solution. Render all notation with KaTeX.
- Record whether I open each worked solution. Treat an unopened solution as an
  unsolved problem and carry that problem into the next daily set at the same
  difficulty. Replace it only after its worked solution has been opened.
- Remember prior problem concepts and structures so later days do not repeat
  them.

## Cars

Show no more than three sampled historical or modern car models. For each one,
include a representative image, its era, defining characteristics, and why it
matters in automotive history or the modern market. Remember previously shown
models.

## Russian poetry

Select one short Russian poem or a self-contained excerpt suitable for
memorisation. Include the Russian text, author, title, and a brief note that
helps with meaning or recall. Avoid previously selected poems.
