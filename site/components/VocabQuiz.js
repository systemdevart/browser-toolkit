"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const VOCAB_FILES = [
  { file: "vocab.json" },
  { file: "vocab-c1.json" },
  { file: "vocab-c2.json" },
  { file: "vocab-pte.json" },
  { file: "vocab-fr-basic.json" },
];

const BANS_API = "/api/vocab/bans";

async function fetchAllBans() {
  try {
    const r = await fetch(BANS_API, { cache: "no-store" });
    if (!r.ok) return {};
    const data = await r.json();
    const out = {};
    const bans = (data && data.bans) || {};
    for (const [srcId, arr] of Object.entries(bans)) {
      if (Array.isArray(arr)) {
        out[srcId] = new Set(arr.map((s) => String(s).toLowerCase()));
      }
    }
    return out;
  } catch (error) {
    console.warn("[vocab] failed to fetch bans", error);
    return {};
  }
}

async function apiBanWord(sourceId, word) {
  try {
    const r = await fetch(`${BANS_API}/${encodeURIComponent(sourceId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ word }),
    });
    return r.ok;
  } catch (error) {
    console.warn("[vocab] ban request failed", error);
    return false;
  }
}

async function apiClearBans(sourceId) {
  try {
    const r = await fetch(`${BANS_API}/${encodeURIComponent(sourceId)}`, {
      method: "DELETE",
    });
    return r.ok;
  } catch (error) {
    console.warn("[vocab] clear bans failed", error);
    return false;
  }
}

function shuffle(items) {
  const out = items.slice();
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

function quizFromItem(item) {
  return {
    word: item.word,
    base: typeof item.base === "string" ? item.base.trim() : "",
    pronunciation:
      typeof item.pronunciation === "string" ? item.pronunciation.trim() : "",
    correct: item.correct,
    options: shuffle([item.correct, ...item.wrong]),
    examples: Array.isArray(item.examples) ? item.examples : [],
  };
}

function pickVoice(language) {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) {
    return null;
  }
  const voices = window.speechSynthesis.getVoices();
  if (!voices.length) return null;
  const requested = language || "en-GB";
  const prefix = requested.split("-")[0].toLowerCase();
  const exact = (voice) => voice.lang.toLowerCase() === requested.toLowerCase();
  const sameLanguage = (voice) =>
    voice.lang.toLowerCase().split("-")[0] === prefix;
  return (
    voices.find(
      (voice) => exact(voice) && /Google|Microsoft|Apple/i.test(voice.name)
    ) ||
    voices.find(exact) ||
    voices.find(
      (voice) =>
        sameLanguage(voice) && /Google|Microsoft|Apple/i.test(voice.name)
    ) ||
    voices.find(sameLanguage) ||
    null
  );
}

function speakWord(text, source) {
  if (
    typeof window === "undefined" ||
    !("speechSynthesis" in window) ||
    !text
  ) {
    return;
  }
  try {
    const language = source?.speechLang || "en-GB";
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = language;
    utter.rate = Number(source?.speechRate) || 0.92;
    utter.pitch = 1;
    const voice = pickVoice(language);
    if (voice) utter.voice = voice;
    window.speechSynthesis.speak(utter);
  } catch (error) {
    console.warn("[vocab] speech failed", error);
  }
}

export default function VocabQuiz() {
  const [sources, setSources] = useState([]);
  const [sourceId, setSourceId] = useState("");
  const [mode, setMode] = useState("idle"); // idle | single | session
  const [currentQuiz, setCurrentQuiz] = useState(null);
  const [revealed, setRevealed] = useState(false);
  const [pickedOption, setPickedOption] = useState(null);
  const [session, setSession] = useState(null); // {order, position, total, correct, answered}
  const [summary, setSummary] = useState(null); // {correct, total}
  const [bannedBySource, setBannedBySource] = useState({}); // { sourceId: Set<lowercased word> }
  const speechSupported =
    typeof window !== "undefined" && "speechSynthesis" in window;

  const nextRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all(
      VOCAB_FILES.map(({ file }) =>
        fetch(`/vocab/${file}`, { cache: "no-store" })
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null)
      )
    ).then((results) => {
      if (cancelled) return;
      const loaded = results
        .filter(
          (payload) =>
            payload &&
            payload.meta &&
            payload.meta.id &&
            Array.isArray(payload.items) &&
            payload.items.length
        )
        .map((payload) => ({
          id: payload.meta.id,
          name: payload.meta.name || payload.meta.id,
          speechLang: payload.meta.speechLang || "en-GB",
          speechLabel: payload.meta.speechLabel || "British English",
          speechRate: payload.meta.speechRate || 0.92,
          exampleLabel: payload.meta.exampleLabel || "Used in a sentence",
          sourceUrl: payload.meta.sourceUrl || "",
          attribution: payload.meta.attribution || "",
          license: payload.meta.license || "",
          licenseUrl: payload.meta.licenseUrl || "",
          items: payload.items,
        }));
      setSources(loaded);
      if (loaded.length && !sourceId) {
        setSourceId(loaded[0].id);
      }
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!speechSupported) return;
    const primeVoices = () => window.speechSynthesis.getVoices();
    primeVoices();
    if (typeof window.speechSynthesis.onvoiceschanged !== "undefined") {
      window.speechSynthesis.onvoiceschanged = primeVoices;
    }
  }, [speechSupported]);

  const activeSource = useMemo(
    () => sources.find((s) => s.id === sourceId) || sources[0] || null,
    [sources, sourceId]
  );

  // Fetch shared bans from the backend once (and whenever the source set changes).
  useEffect(() => {
    let cancelled = false;
    fetchAllBans().then((byId) => {
      if (cancelled) return;
      setBannedBySource(byId);
    });
    return () => {
      cancelled = true;
    };
  }, [sources]);

  const activeBanned = useMemo(() => {
    if (!activeSource) return new Set();
    return bannedBySource[activeSource.id] || new Set();
  }, [activeSource, bannedBySource]);

  const activeItems = useMemo(() => {
    if (!activeSource) return [];
    if (!activeBanned.size) return activeSource.items;
    return activeSource.items.filter(
      (item) => !activeBanned.has(String(item.word).toLowerCase())
    );
  }, [activeSource, activeBanned]);

  const banCurrentWord = useCallback(() => {
    if (!currentQuiz || !activeSource) return;
    const word = String(currentQuiz.word).toLowerCase();
    const srcId = activeSource.id;
    // Optimistic UI: assume the API will accept, roll back on failure.
    setBannedBySource((prev) => {
      const prevSet = prev[srcId] || new Set();
      if (prevSet.has(word)) return prev;
      const nextSet = new Set(prevSet);
      nextSet.add(word);
      return { ...prev, [srcId]: nextSet };
    });
    apiBanWord(srcId, word).then((ok) => {
      if (ok) return;
      setBannedBySource((prev) => {
        const set = new Set(prev[srcId] || []);
        set.delete(word);
        return { ...prev, [srcId]: set };
      });
    });
  }, [currentQuiz, activeSource]);

  const unbanAll = useCallback(() => {
    if (!activeSource) return;
    const srcId = activeSource.id;
    const previous = bannedBySource[srcId] || new Set();
    setBannedBySource((prev) => ({ ...prev, [srcId]: new Set() }));
    apiClearBans(srcId).then((ok) => {
      if (ok) return;
      setBannedBySource((prev) => ({ ...prev, [srcId]: previous }));
    });
  }, [activeSource, bannedBySource]);

  const isCurrentBanned =
    !!currentQuiz && activeBanned.has(String(currentQuiz.word).toLowerCase());

  const startSingle = useCallback(() => {
    if (!activeItems.length) return;
    const item = activeItems[Math.floor(Math.random() * activeItems.length)];
    const quiz = quizFromItem(item);
    setSession(null);
    setSummary(null);
    setMode("single");
    setCurrentQuiz(quiz);
    setRevealed(false);
    setPickedOption(null);
    speakWord(quiz.word, activeSource);
  }, [activeItems, activeSource]);

  const startSession = useCallback(() => {
    if (!activeItems.length) return;
    // Snapshot the item list at session start; banning mid-session only takes
    // effect for future sessions, not the current shuffled order.
    const snapshot = activeItems.slice();
    const order = shuffle(snapshot.map((_, idx) => idx));
    const firstQuiz = quizFromItem(snapshot[order[0]]);
    setSession({
      order,
      snapshot,
      position: 0,
      total: order.length,
      correct: 0,
      answered: 0,
    });
    setSummary(null);
    setMode("session");
    setCurrentQuiz(firstQuiz);
    setRevealed(false);
    setPickedOption(null);
    speakWord(firstQuiz.word, activeSource);
  }, [activeItems, activeSource]);

  const advance = useCallback(() => {
    if (session) {
      const nextPosition = session.position + 1;
      if (nextPosition >= session.total) {
        setSummary({ correct: session.correct, total: session.total });
        setCurrentQuiz(null);
        return;
      }
      const nextIdx = session.order[nextPosition];
      const list = session.snapshot || activeItems;
      const quiz = quizFromItem(list[nextIdx]);
      setSession({ ...session, position: nextPosition });
      setCurrentQuiz(quiz);
      setRevealed(false);
      setPickedOption(null);
      speakWord(quiz.word, activeSource);
    } else if (mode === "single") {
      startSingle();
    }
  }, [session, activeItems, mode, startSingle, activeSource]);

  const handleAnswer = useCallback(
    (option) => {
      if (!currentQuiz || pickedOption) return;
      setPickedOption(option);
      const isCorrect = option === currentQuiz.correct;
      if (session) {
        setSession((prev) =>
          prev
            ? {
                ...prev,
                answered: prev.answered + 1,
                correct: prev.correct + (isCorrect ? 1 : 0),
              }
            : prev
        );
      }
      // Focus the "Next" button so the user can hit Enter/Space to advance.
      setTimeout(() => nextRef.current?.focus(), 0);
    },
    [currentQuiz, pickedOption, session]
  );

  const reset = useCallback(() => {
    setMode("idle");
    setCurrentQuiz(null);
    setSession(null);
    setSummary(null);
    setRevealed(false);
    setPickedOption(null);
  }, []);

  // Empty state — no vocab loaded yet or files missing.
  if (!sources.length) {
    return (
      <div className="vocab-card">
        <div className="vocab-empty">
          Loading vocab… If nothing appears, no vocab JSON files were built into{" "}
          <code>/vocab/</code>. Run <code>npm run extract-vocab</code> and
          rebuild.
        </div>
      </div>
    );
  }

  return (
    <div className="vocab-card">
      <div className="vocab-source-picker">
        <label htmlFor="vocab-source">Source</label>
        <select
          id="vocab-source"
          value={sourceId}
          onChange={(event) => {
            setSourceId(event.target.value);
            reset();
          }}
        >
          {sources.map((s) => {
            const bannedInSrc = (bannedBySource[s.id] || new Set()).size;
            const effective = s.items.length - bannedInSrc;
            return (
              <option key={s.id} value={s.id}>
                {s.name} ({effective}
                {bannedInSrc ? ` · ${bannedInSrc} banned` : ""})
              </option>
            );
          })}
        </select>
        {activeBanned.size > 0 && (
          <div className="vocab-banned-hint">
            <span>{activeBanned.size} banned in this source</span>
            <button
              type="button"
              className="vocab-banned-reset"
              onClick={unbanAll}
            >
              Unban all
            </button>
          </div>
        )}
      </div>

      {activeSource?.attribution && (
        <div className="vocab-source-attribution">
          Source:{" "}
          <a href={activeSource.sourceUrl} target="_blank" rel="noreferrer">
            {activeSource.attribution}
          </a>
          {activeSource.license && (
            <>
              {" - "}
              <a
                href={activeSource.licenseUrl}
                target="_blank"
                rel="noreferrer"
              >
                {activeSource.license}
              </a>
            </>
          )}
        </div>
      )}

      {mode === "idle" && (
        <div className="vocab-controls">
          <button
            type="button"
            className="btn-primary"
            onClick={startSingle}
            disabled={!activeItems.length}
          >
            Show me a word
          </button>
          <button
            type="button"
            className="btn-session"
            onClick={startSession}
            disabled={!activeItems.length}
          >
            Study all {activeItems.length} words
          </button>
        </div>
      )}

      {(mode === "single" || mode === "session") && currentQuiz && !summary && (
        <>
          {session && (
            <div className="vocab-progress">
              <span className="vocab-progress-counter">
                {session.position + 1} /{" "}
                {Math.max(activeItems.length, session.position + 1)}
              </span>
              <span className="vocab-progress-score">
                Score: {session.correct}
              </span>
            </div>
          )}

          <div className="vocab-word-block">
            <div className="vocab-word">{currentQuiz.word}</div>
            {currentQuiz.base &&
              currentQuiz.base.toLowerCase() !==
                currentQuiz.word.toLowerCase() && (
                <div className="vocab-base">base: {currentQuiz.base}</div>
              )}
            {currentQuiz.pronunciation && (
              <div className="vocab-pronunciation">
                Pronunciation: {currentQuiz.pronunciation}
              </div>
            )}
            {speechSupported && (
              <button
                type="button"
                className="vocab-speak"
                onClick={() => speakWord(currentQuiz.word, activeSource)}
                title={`Play pronunciation (${activeSource.speechLabel})`}
                aria-label={`Play pronunciation (${activeSource.speechLabel})`}
              >
                <span aria-hidden="true">🔊</span>
                <span>Play ({activeSource.speechLabel})</span>
              </button>
            )}
          </div>

          {!revealed && (
            <button
              type="button"
              className="vocab-reveal"
              onClick={(event) => {
                // Clear focus before the button unmounts: iOS Safari otherwise
                // keeps :hover/:focus on whichever new button ends up under the
                // last touch point (usually option 2 or 3).
                event.currentTarget.blur();
                setRevealed(true);
              }}
            >
              Reveal choices
            </button>
          )}

          {revealed && (
            <div className="vocab-options">
              {currentQuiz.options.map((option) => {
                let state = "";
                if (pickedOption) {
                  if (option === currentQuiz.correct) state = "correct";
                  else if (option === pickedOption) state = "wrong";
                }
                return (
                  <button
                    key={option}
                    type="button"
                    className="vocab-option"
                    data-state={state || undefined}
                    disabled={!!pickedOption}
                    onClick={() => handleAnswer(option)}
                  >
                    {option}
                  </button>
                );
              })}
            </div>
          )}

          {pickedOption && (
            <>
              <div
                className="vocab-feedback"
                data-state={
                  pickedOption === currentQuiz.correct ? "correct" : "wrong"
                }
              >
                {pickedOption === currentQuiz.correct
                  ? "Correct."
                  : `Correct answer: ${currentQuiz.correct}`}
              </div>

              {currentQuiz.examples.length > 0 && (
                <div className="vocab-examples">
                  <div className="vocab-examples-title">
                    {activeSource.exampleLabel}
                  </div>
                  <ol className="vocab-examples-list">
                    {currentQuiz.examples.map((sentence, i) => (
                      <li key={i}>{sentence}</li>
                    ))}
                  </ol>
                </div>
              )}

              <div className="vocab-answered-actions">
                <button
                  type="button"
                  className="vocab-next"
                  ref={nextRef}
                  onClick={advance}
                >
                  {session && session.position + 1 >= session.total
                    ? "See results"
                    : "Next word"}
                </button>
                <button
                  type="button"
                  className="vocab-ban"
                  onClick={banCurrentWord}
                  disabled={isCurrentBanned}
                  title="Never show this word again on this device"
                >
                  {isCurrentBanned ? "Banned" : "Ban this word"}
                </button>
              </div>
            </>
          )}
        </>
      )}

      {summary && (
        <div className="vocab-summary">
          <div className="vocab-summary-title">Session complete</div>
          <div className="vocab-summary-score">
            {summary.correct} / {summary.total} correct
          </div>
          <div className="vocab-summary-percent">
            {summary.total > 0
              ? Math.round((summary.correct / summary.total) * 100)
              : 0}
            %
          </div>
          <div className="vocab-summary-actions">
            <button
              type="button"
              className="vocab-reveal"
              onClick={startSession}
            >
              Study again
            </button>
            <button type="button" className="vocab-next" onClick={reset}>
              Back
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
