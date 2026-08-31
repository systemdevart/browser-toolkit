const QuizRuntime = globalThis.LiterateGoggles || {};
const QUIZ_VOCAB_SOURCES = Array.isArray(QuizRuntime.vocabSources)
  ? QuizRuntime.vocabSources.filter(
      (s) =>
        s &&
        typeof s.id === "string" &&
        Array.isArray(s.items) &&
        s.items.length
    )
  : [];
const QUIZ_VOCAB_FALLBACK = Array.isArray(QuizRuntime.vocab)
  ? QuizRuntime.vocab
  : [];
const QUIZ_VOCAB_CURRENT_KEY = "literategoggles.features.englishVocab.current";

function pickSourceItems(sourceId) {
  if (sourceId) {
    const match = QUIZ_VOCAB_SOURCES.find((s) => s.id === sourceId);
    if (match) return match;
  }
  if (QUIZ_VOCAB_SOURCES.length) {
    return QUIZ_VOCAB_SOURCES[0];
  }
  return {
    name: "",
    items: QUIZ_VOCAB_FALLBACK,
    speechLang: "en-GB",
    speechLabel: "British English",
    speechRate: 0.92,
    exampleLabel: "Used in a sentence",
  };
}

const speechSupported =
  typeof window !== "undefined" && "speechSynthesis" in window;

function pickVoice(language) {
  if (!speechSupported) return null;
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

function speakWord(text, language = "en-GB", rate = 0.92) {
  if (!speechSupported || !text) return;
  try {
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = language;
    utter.rate = Number(rate) || 0.92;
    utter.pitch = 1;
    const voice = pickVoice(language);
    if (voice) utter.voice = voice;
    window.speechSynthesis.speak(utter);
  } catch (error) {
    console.warn("LiterateGoggles: speech failed.", error);
  }
}

function warmUpVoices() {
  if (!speechSupported) return;
  window.speechSynthesis.getVoices();
  if (typeof window.speechSynthesis.onvoiceschanged !== "undefined") {
    window.speechSynthesis.onvoiceschanged = () => {
      window.speechSynthesis.getVoices();
    };
  }
}

function quizShuffle(items) {
  const copy = items.slice();
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

function quizFromItem(item, source = {}) {
  return {
    word: item.word,
    base: typeof item.base === "string" ? item.base.trim() : "",
    pronunciation:
      typeof item.pronunciation === "string" ? item.pronunciation.trim() : "",
    correct: item.correct,
    options: quizShuffle([item.correct, ...item.wrong]),
    examples: Array.isArray(item.examples) ? item.examples : [],
    speechLang: source.speechLang || "en-GB",
    speechLabel: source.speechLabel || "British English",
    speechRate: source.speechRate || 0.92,
    exampleLabel: source.exampleLabel || "Used in a sentence",
    sourceUrl: source.sourceUrl || "",
    attribution: source.attribution || "",
    license: source.license || "",
    licenseUrl: source.licenseUrl || "",
  };
}

async function readStoredQuiz() {
  try {
    const result = await chrome.storage.local.get([QUIZ_VOCAB_CURRENT_KEY]);
    const current = result[QUIZ_VOCAB_CURRENT_KEY];
    if (
      current &&
      typeof current.word === "string" &&
      typeof current.correct === "string" &&
      Array.isArray(current.options)
    ) {
      return current;
    }
  } catch (error) {
    console.warn("LiterateGoggles: failed to read stored quiz.", error);
  }
  return null;
}

async function requestFreshQuiz() {
  try {
    const response = await chrome.runtime.sendMessage({
      type: "literategoggles/pick-next-word",
    });
    if (response && response.ok) {
      const stored = await readStoredQuiz();
      if (stored) {
        return stored;
      }
    }
  } catch (error) {
    console.warn(
      "LiterateGoggles: background pick failed; using local pick.",
      error
    );
  }
  const fallbackSource = pickSourceItems(null);
  if (!fallbackSource.items.length) {
    return null;
  }
  const item =
    fallbackSource.items[
      Math.floor(Math.random() * fallbackSource.items.length)
    ];
  return quizFromItem(item, fallbackSource);
}

document.addEventListener("DOMContentLoaded", () => {
  const progressEl = document.getElementById("vocab-progress");
  const progressCounter = document.getElementById("vocab-progress-counter");
  const progressScore = document.getElementById("vocab-progress-score");
  const bodyEl = document.getElementById("vocab-body");
  const wordEl = document.getElementById("vocab-word");
  const revealButton = document.getElementById("vocab-reveal");
  const optionsEl = document.getElementById("vocab-options");
  const feedbackEl = document.getElementById("vocab-feedback");
  const nextButton = document.getElementById("vocab-next");
  const speakButton = document.getElementById("vocab-speak");
  const baseEl = document.getElementById("vocab-base");
  const pronunciationEl = document.getElementById("vocab-pronunciation");
  const examplesEl = document.getElementById("vocab-examples");
  const examplesTitle = document.querySelector(".vocab-examples-title");
  const attributionEl = document.getElementById("vocab-source-attribution");
  const examplesList = document.getElementById("vocab-examples-list");
  const summaryEl = document.getElementById("vocab-summary");
  const summaryScore = document.getElementById("vocab-summary-score");
  const summaryPercent = document.getElementById("vocab-summary-percent");
  const restartButton = document.getElementById("vocab-restart");
  const summaryCloseButton = document.getElementById("vocab-summary-close");

  const params = new URLSearchParams(window.location.search);
  const initialMode = params.get("mode") === "session" ? "session" : "single";
  const requestedSource = params.get("source") || null;
  const activeSource = pickSourceItems(requestedSource);
  const activeItems = activeSource.items;

  let currentQuiz = null;
  let session = null;

  function resetBodyView() {
    optionsEl.innerHTML = "";
    optionsEl.hidden = true;
    feedbackEl.textContent = "";
    feedbackEl.hidden = true;
    feedbackEl.dataset.state = "";
    examplesList.innerHTML = "";
    examplesEl.hidden = true;
    nextButton.hidden = true;
    revealButton.hidden = false;
    revealButton.disabled = false;
    revealButton.textContent = "Reveal choices";
  }

  function renderExamples(examples) {
    examplesList.innerHTML = "";
    if (!Array.isArray(examples) || !examples.length) {
      examplesEl.hidden = true;
      return;
    }
    examples.forEach((sentence) => {
      const li = document.createElement("li");
      li.textContent = sentence;
      examplesList.appendChild(li);
    });
    examplesEl.hidden = false;
  }

  function showBody() {
    bodyEl.hidden = false;
    summaryEl.hidden = true;
  }

  function showSummary(correct, total) {
    bodyEl.hidden = true;
    summaryEl.hidden = false;
    summaryScore.textContent = `${correct} / ${total} correct`;
    const pct = total > 0 ? Math.round((correct / total) * 100) : 0;
    summaryPercent.textContent = `${pct}%`;
  }

  function updateProgress() {
    if (!session) {
      progressEl.hidden = true;
      return;
    }
    progressEl.hidden = false;
    const position = Math.min(session.position + 1, session.total);
    progressCounter.textContent = `${position} / ${session.total}`;
    progressScore.textContent = `Score: ${session.correct}`;
  }

  function renderQuiz(quiz) {
    currentQuiz = quiz;
    showBody();
    resetBodyView();
    wordEl.textContent = quiz ? quiz.word : "—";
    if (baseEl) {
      const base = quiz && quiz.base ? quiz.base : "";
      if (base && base.toLowerCase() !== (quiz.word || "").toLowerCase()) {
        baseEl.textContent = `base: ${base}`;
        baseEl.hidden = false;
      } else {
        baseEl.textContent = "";
        baseEl.hidden = true;
      }
    }
    if (pronunciationEl) {
      const pronunciation =
        quiz && quiz.pronunciation ? quiz.pronunciation : "";
      pronunciationEl.textContent = pronunciation
        ? `Pronunciation: ${pronunciation}`
        : "";
      pronunciationEl.hidden = !pronunciation;
    }
    if (speakButton) {
      speakButton.disabled = !quiz || !speechSupported;
      speakButton.hidden = !speechSupported;
      const label = quiz?.speechLabel || "British English";
      speakButton.title = `Play pronunciation (${label})`;
      speakButton.setAttribute("aria-label", speakButton.title);
      const text = speakButton.querySelector("span:last-child");
      if (text) text.textContent = `Play (${label})`;
    }
    if (examplesTitle) {
      examplesTitle.textContent = quiz?.exampleLabel || "Used in a sentence";
    }
    if (attributionEl) {
      attributionEl.replaceChildren();
      if (quiz?.attribution && quiz?.sourceUrl) {
        attributionEl.append("Source: ");
        const sourceLink = document.createElement("a");
        sourceLink.href = quiz.sourceUrl;
        sourceLink.target = "_blank";
        sourceLink.rel = "noreferrer";
        sourceLink.textContent = quiz.attribution;
        attributionEl.append(sourceLink);
        if (quiz.license) {
          attributionEl.append(" - ");
          const licenseLink = document.createElement("a");
          licenseLink.href = quiz.licenseUrl;
          licenseLink.target = "_blank";
          licenseLink.rel = "noreferrer";
          licenseLink.textContent = quiz.license;
          attributionEl.append(licenseLink);
        }
        attributionEl.hidden = false;
      } else {
        attributionEl.hidden = true;
      }
    }
    if (!quiz) {
      revealButton.disabled = true;
      revealButton.textContent = "No vocab available";
    } else if (speechSupported) {
      speakWord(quiz.word, quiz.speechLang, quiz.speechRate);
    }
    nextButton.textContent =
      session && session.position + 1 >= session.total
        ? "See results"
        : "Next word";
    updateProgress();
  }

  function renderOptions() {
    if (!currentQuiz) {
      return;
    }
    revealButton.hidden = true;
    optionsEl.hidden = false;
    optionsEl.innerHTML = "";
    currentQuiz.options.forEach((option) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "vocab-option";
      btn.textContent = option;
      btn.addEventListener("click", () => handleAnswer(option, btn));
      optionsEl.appendChild(btn);
    });
  }

  function handleAnswer(option, clickedBtn) {
    if (!currentQuiz) {
      return;
    }
    const isCorrect = option === currentQuiz.correct;
    optionsEl.querySelectorAll("button").forEach((btn) => {
      btn.disabled = true;
      if (btn.textContent === currentQuiz.correct) {
        btn.dataset.state = "correct";
      } else if (btn === clickedBtn) {
        btn.dataset.state = "wrong";
      }
    });
    feedbackEl.hidden = false;
    feedbackEl.dataset.state = isCorrect ? "correct" : "wrong";
    feedbackEl.textContent = isCorrect
      ? "Correct."
      : `Correct answer: ${currentQuiz.correct}`;
    renderExamples(currentQuiz.examples);
    if (session) {
      session.answered += 1;
      if (isCorrect) {
        session.correct += 1;
      }
      updateProgress();
    }
    nextButton.hidden = false;
    nextButton.focus();
  }

  async function loadSingle() {
    session = null;
    updateProgress();
    showBody();
    resetBodyView();
    wordEl.textContent = "…";
    let quiz = null;
    if (requestedSource && activeItems.length) {
      const item = activeItems[Math.floor(Math.random() * activeItems.length)];
      quiz = quizFromItem(item, activeSource);
    } else {
      quiz = (await readStoredQuiz()) || (await requestFreshQuiz());
    }
    renderQuiz(quiz);
  }

  function startSession() {
    if (!activeItems.length) {
      renderQuiz(null);
      return;
    }
    session = {
      order: quizShuffle(activeItems.map((_, idx) => idx)),
      position: 0,
      total: activeItems.length,
      correct: 0,
      answered: 0,
    };
    renderCurrentSessionWord();
  }

  function renderCurrentSessionWord() {
    if (!session) {
      return;
    }
    const idx = session.order[session.position];
    renderQuiz(quizFromItem(activeItems[idx], activeSource));
  }

  function advanceSession() {
    if (!session) {
      return;
    }
    session.position += 1;
    if (session.position >= session.total) {
      showSummary(session.correct, session.total);
      progressEl.hidden = false;
      progressCounter.textContent = `${session.total} / ${session.total}`;
      progressScore.textContent = `Score: ${session.correct}`;
      return;
    }
    renderCurrentSessionWord();
  }

  function handleNext() {
    if (session) {
      advanceSession();
    } else {
      loadSingle();
    }
  }

  function closeTab() {
    window.close();
  }

  revealButton.addEventListener("click", renderOptions);
  nextButton.addEventListener("click", handleNext);
  restartButton.addEventListener("click", startSession);
  summaryCloseButton.addEventListener("click", closeTab);
  if (speakButton) {
    speakButton.addEventListener("click", () => {
      if (currentQuiz) {
        speakWord(
          currentQuiz.word,
          currentQuiz.speechLang,
          currentQuiz.speechRate
        );
      }
    });
  }
  warmUpVoices();

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeTab();
    }
  });

  if (initialMode === "session") {
    startSession();
  } else {
    loadSingle();
  }
});
