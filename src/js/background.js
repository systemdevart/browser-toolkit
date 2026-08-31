try {
  importScripts("features.js");
} catch (error) {
  console.warn(
    "LiterateGoggles: unable to load shared feature metadata in background script.",
    error
  );
}

for (const script of [
  "vocab.js",
  "vocab-c1.js",
  "vocab-c2.js",
  "vocab-pte.js",
  "vocab-fr-basic.js",
]) {
  try {
    importScripts(script);
  } catch (error) {
    console.warn(
      `LiterateGoggles: unable to load ${script} in background script.`,
      error
    );
  }
}

const LiterateGogglesRuntime = globalThis.LiterateGoggles || {};
const GLOBAL_STORAGE_KEY =
  LiterateGogglesRuntime.globalStorageKey || "literategoggles.globalEnabled";
const VOCAB_ENABLED_KEY = "literategoggles.features.englishVocab.enabled";
const VOCAB_INDEX_KEY = "literategoggles.features.englishVocab.index";
const VOCAB_CURRENT_KEY = "literategoggles.features.englishVocab.current";
const VOCAB_ALARM_NAME = "literategoggles.vocab.tick";
const VOCAB_INTERVAL_MINUTES = 15;
const VOCAB_NOTIFICATION_ID = "literategoggles-vocab-notification";

function getVocabSource() {
  const lg = globalThis.LiterateGoggles || {};
  if (Array.isArray(lg.vocab) && lg.vocab.length) {
    return { items: lg.vocab };
  }
  if (Array.isArray(lg.vocabSources)) {
    const first = lg.vocabSources.find(
      (s) => s && Array.isArray(s.items) && s.items.length
    );
    if (first) return first;
  }
  return { items: [] };
}

function updateIcon(isEnabled) {
  const iconState = isEnabled ? "on" : "off";
  const iconPath = chrome.runtime.getURL(`icons/${iconState}.png`);
  chrome.action.setIcon({
    path: {
      16: iconPath,
      24: iconPath,
      32: iconPath,
      48: iconPath,
      128: iconPath,
    },
  });
}

function refreshIconFromStorage() {
  chrome.storage.sync.get([GLOBAL_STORAGE_KEY], (result) => {
    const isEnabled = result[GLOBAL_STORAGE_KEY] !== false;
    updateIcon(isEnabled);
  });
}

async function readVocabSettings() {
  const [syncResult, localResult] = await Promise.all([
    chrome.storage.sync.get([GLOBAL_STORAGE_KEY, VOCAB_ENABLED_KEY]),
    chrome.storage.local.get([VOCAB_INDEX_KEY]),
  ]);
  const globalEnabled = syncResult[GLOBAL_STORAGE_KEY] !== false;
  const vocabEnabled = syncResult[VOCAB_ENABLED_KEY] !== false;
  const rawIndex = localResult[VOCAB_INDEX_KEY];
  const index =
    typeof rawIndex === "number" && Number.isFinite(rawIndex) && rawIndex >= 0
      ? rawIndex
      : 0;
  return { globalEnabled, vocabEnabled, index };
}

async function ensureVocabAlarm() {
  const { globalEnabled, vocabEnabled } = await readVocabSettings();
  const shouldRun =
    globalEnabled && vocabEnabled && getVocabSource().items.length > 0;
  const existing = await chrome.alarms.get(VOCAB_ALARM_NAME);
  if (shouldRun) {
    if (!existing) {
      chrome.alarms.create(VOCAB_ALARM_NAME, {
        delayInMinutes: VOCAB_INTERVAL_MINUTES,
        periodInMinutes: VOCAB_INTERVAL_MINUTES,
      });
      console.info(
        `LiterateGoggles: vocab alarm scheduled every ${VOCAB_INTERVAL_MINUTES}m.`
      );
    }
  } else if (existing) {
    chrome.alarms.clear(VOCAB_ALARM_NAME);
    console.info("LiterateGoggles: vocab alarm cleared.");
  }
}

function shuffle(items) {
  const copy = items.slice();
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

function buildQuizPayload(item, source) {
  const options = shuffle([item.correct, ...item.wrong]);
  return {
    word: item.word,
    base: typeof item.base === "string" ? item.base : "",
    pronunciation:
      typeof item.pronunciation === "string" ? item.pronunciation : "",
    correct: item.correct,
    options,
    examples: Array.isArray(item.examples) ? item.examples : [],
    speechLang: source.speechLang || "en-GB",
    speechLabel: source.speechLabel || "British English",
    speechRate: source.speechRate || 0.92,
    exampleLabel: source.exampleLabel || "Used in a sentence",
    sourceUrl: source.sourceUrl || "",
    attribution: source.attribution || "",
    license: source.license || "",
    licenseUrl: source.licenseUrl || "",
    generatedAt: Date.now(),
  };
}

async function pickNextWord() {
  const source = getVocabSource();
  const vocab = source.items;
  if (!vocab.length) {
    return null;
  }
  const { index } = await readVocabSettings();
  const nextIndex = index % vocab.length;
  const item = vocab[nextIndex];
  await chrome.storage.local.set({
    [VOCAB_INDEX_KEY]: (nextIndex + 1) % vocab.length,
    [VOCAB_CURRENT_KEY]: buildQuizPayload(item, source),
  });
  return item;
}

async function fireVocabNotification() {
  const item = await pickNextWord();
  if (!item) {
    return;
  }
  try {
    chrome.notifications.create(VOCAB_NOTIFICATION_ID, {
      type: "basic",
      iconUrl: chrome.runtime.getURL("icons/on.png"),
      title: `Vocab: ${item.word}`,
      message:
        "Open the LiterateGoggles popup and reveal the choices to test yourself.",
      priority: 1,
      requireInteraction: false,
    });
    console.info(
      `LiterateGoggles: vocab notification fired for "${item.word}".`
    );
  } catch (error) {
    console.warn("LiterateGoggles: failed to fire vocab notification.", error);
  }
}

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== VOCAB_ALARM_NAME) {
    return;
  }
  const { globalEnabled, vocabEnabled } = await readVocabSettings();
  if (!globalEnabled || !vocabEnabled) {
    return;
  }
  await fireVocabNotification();
});

chrome.notifications.onClicked.addListener((notificationId) => {
  if (notificationId !== VOCAB_NOTIFICATION_ID) {
    return;
  }
  const url = chrome.runtime.getURL("quiz.html?mode=single");
  chrome.tabs.create({ url });
  chrome.notifications.clear(notificationId);
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || typeof message !== "object") {
    return false;
  }
  if (message.type === "literategoggles/pick-next-word") {
    pickNextWord()
      .then((item) => sendResponse({ ok: true, item }))
      .catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  }
  return false;
});

chrome.runtime.onInstalled.addListener(async () => {
  refreshIconFromStorage();
  await ensureVocabAlarm();
});
if (
  chrome.runtime.onStartup &&
  typeof chrome.runtime.onStartup.addListener === "function"
) {
  chrome.runtime.onStartup.addListener(async () => {
    refreshIconFromStorage();
    await ensureVocabAlarm();
  });
}

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "sync") {
    if (GLOBAL_STORAGE_KEY in changes) {
      updateIcon(changes[GLOBAL_STORAGE_KEY].newValue !== false);
    }
    if (GLOBAL_STORAGE_KEY in changes || VOCAB_ENABLED_KEY in changes) {
      ensureVocabAlarm();
    }
  }
});

refreshIconFromStorage();
ensureVocabAlarm();
