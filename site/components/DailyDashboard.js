"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import DailyChessDrills from "./DailyChessDrills";
import DailyConceptMemory from "./DailyConceptMemory";
import DailyMathPractice from "./DailyMathPractice";
import DailyOpeningNames from "./DailyOpeningNames";
import DailyTimers from "./DailyTimers";

const PRACTICE_LINKS = [
  {
    href: "/vocab/",
    number: "01",
    title: "Vocabulary",
    description:
      "Build recall with focused English and French vocabulary practice.",
  },
  {
    href: "https://sandbox.chebakov.me/ielts-speaking/",
    number: "02",
    title: "IELTS speaking",
    description: "Record a timed answer and get audio-aware feedback.",
  },
  {
    href: "https://sandbox.chebakov.me/ielts-writing/",
    number: "03",
    title: "IELTS writing",
    description: "Practice a complete task with band 7.5 guidance.",
  },
];

const HISTORY_LABELS = {
  event: "Event",
  holiday: "Holiday",
  birthday: "Born today",
};

const SAYING_GROUPS = [
  {
    language: "ru",
    label: "Russian",
    note: "Крылатые фразы и пословицы",
  },
  {
    language: "en",
    label: "English",
    note: "Catchphrases and proverbs",
  },
];

const SHOW_CHESS_OPENING_RECALL = false;

async function responseError(response) {
  try {
    const payload = await response.json();
    if (typeof payload?.detail === "string") return payload.detail;
  } catch {
    // Use the status fallback.
  }
  return `Request failed (${response.status})`;
}

function LoadingDashboard() {
  return (
    <div className="daily-loading" role="status" aria-live="polite">
      <div className="daily-loading-mark" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <div>
        <strong>Preparing today's brief</strong>
        <p>
          Reading history and ML sources, then selecting cars and poetry. The
          first daily refresh can take a little while.
        </p>
      </div>
    </div>
  );
}

function SectionHeading({ eyebrow, title, note, headingId }) {
  return (
    <div className="daily-section-heading">
      <div>
        <span>{eyebrow}</span>
        <h2 id={headingId}>{title}</h2>
      </div>
      {note && <p>{note}</p>}
    </div>
  );
}

function SourceLink({ href, children }) {
  return (
    <a href={href} target="_blank" rel="noreferrer">
      {children}
      <span aria-hidden="true">↗</span>
    </a>
  );
}

export default function DailyDashboard() {
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadDigest = useCallback(async () => {
    setError(null);
    try {
      const response = await fetch("/api/daily", { cache: "no-store" });
      if (!response.ok) throw new Error(await responseError(response));
      const next = await response.json();
      setPayload(next);
    } catch (loadError) {
      setError(loadError.message || "Could not load today's digest.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDigest();
    const interval = window.setInterval(() => void loadDigest(), 5 * 60 * 1000);
    return () => window.clearInterval(interval);
  }, [loadDigest]);

  const digest = payload?.digest;
  const generatedTime = digest
    ? new Intl.DateTimeFormat(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        timeZoneName: "short",
      }).format(new Date(digest.generatedAt))
    : "";

  return (
    <div className="daily-dashboard">
      <header className="daily-hero">
        <div className="daily-brand-row">
          <Link href="/" className="daily-brand">
            daily.chebakov.me
          </Link>
          <div className="daily-account-actions">
            {digest && (
              <span className="daily-generated">
                Updated {generatedTime}
                {payload.stale ? " (saved edition)" : ""}
              </span>
            )}
            <a href="/auth/logout" className="daily-sign-out">
              Sign out
            </a>
          </div>
        </div>
        <div className="daily-hero-copy">
          <span className="daily-kicker">Morning routine</span>
          <h1>A thoughtful start, prepared for you.</h1>
          <p>
            Practice English, revisit history, scan new machine learning work,
            keep a few good sayings, learn a car, and memorise a little Russian
            poetry.
          </p>
        </div>
        {digest && (
          <div className="daily-date-line">
            <time dateTime={digest.date}>{digest.displayDate}</time>
            <span>{digest.timezone}</span>
          </div>
        )}
      </header>

      <section className="daily-routine" aria-labelledby="practice-heading">
        <SectionHeading
          eyebrow="Start here"
          title="IELTS practice"
          note="Three focused tools, ready when you are."
          headingId="practice-heading"
        />
        <div className="daily-practice-grid">
          {PRACTICE_LINKS.map((item) => (
            <Link
              className="daily-practice-card"
              href={item.href}
              key={item.href}
            >
              <span className="daily-practice-number">{item.number}</span>
              <div>
                <h3>{item.title}</h3>
                <p>{item.description}</p>
              </div>
              <span className="daily-card-arrow" aria-hidden="true">
                →
              </span>
            </Link>
          ))}
        </div>
      </section>

      <DailyConceptMemory />

      {SHOW_CHESS_OPENING_RECALL && <DailyChessDrills />}

      <DailyOpeningNames />

      {loading && !digest && <LoadingDashboard />}

      {error && !digest && (
        <section className="daily-load-error" role="alert">
          <span>Daily research is temporarily unavailable.</span>
          <p>{error}</p>
          <button type="button" onClick={() => void loadDigest()}>
            Try again
          </button>
        </section>
      )}

      {payload?.warning && (
        <div className="daily-warning" role="status">
          {payload.warning}
        </div>
      )}

      {digest && (
        <>
          <section className="daily-section" aria-labelledby="history-heading">
            <SectionHeading
              eyebrow="Then and now"
              title="On this day"
              note="A bilingual selection from today's date pages."
              headingId="history-heading"
            />
            <div className="daily-history-grid">
              {digest.onThisDay.map((item, index) => (
                <article
                  className="daily-history-card"
                  key={`${item.language}-${item.category}-${item.title}-${index}`}
                  lang={item.language}
                >
                  <div className="daily-history-meta">
                    <span>{HISTORY_LABELS[item.category]}</span>
                    <span>{item.language.toUpperCase()}</span>
                  </div>
                  <div className="daily-history-year">
                    {item.year || "Today"}
                  </div>
                  <h3>{item.title}</h3>
                  <p>{item.detail}</p>
                  <SourceLink href={item.sourceUrl}>
                    {item.language === "ru"
                      ? "Russian Wikipedia"
                      : "English Wikipedia"}
                  </SourceLink>
                </article>
              ))}
            </div>
          </section>

          <section
            className="daily-section daily-sayings-section"
            aria-labelledby="sayings-heading"
          >
            <SectionHeading
              eyebrow="Words in circulation"
              title="Sayings worth keeping"
              note="Three Russian and three English proverbs sampled from the full source collections."
              headingId="sayings-heading"
            />
            <div className="daily-sayings-languages">
              {SAYING_GROUPS.map((group) => (
                <div
                  className="daily-sayings-language"
                  data-language={group.language}
                  key={group.language}
                  lang={group.language}
                >
                  <div className="daily-sayings-language-heading">
                    <span>{group.label}</span>
                    <p>{group.note}</p>
                  </div>
                  <div className="daily-sayings-list">
                    {(digest.sayings || [])
                      .filter((saying) => saying.language === group.language)
                      .map((saying, index) => (
                        <article className="daily-saying-card" key={saying.id}>
                          <span className="daily-saying-number">
                            {String(index + 1).padStart(2, "0")}
                          </span>
                          <blockquote>{saying.text}</blockquote>
                          {saying.translation && (
                            <div className="daily-saying-translation">
                              <strong>
                                {group.language === "ru"
                                  ? "English translation"
                                  : "Перевод на русский"}
                              </strong>
                              <span>{saying.translation}</span>
                            </div>
                          )}
                          <p>{saying.meaning}</p>
                          <div className="daily-saying-origin">
                            <strong>Origin / use</strong>
                            <span>{saying.origin}</span>
                          </div>
                          <SourceLink href={saying.sourceUrl}>
                            {saying.sourceLabel}
                          </SourceLink>
                        </article>
                      ))}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section
            className="daily-section daily-research-section"
            aria-labelledby="research-heading"
          >
            <SectionHeading
              eyebrow="Research radar"
              title="Machine learning"
              note="Selected for NLP, generative models, and image generation."
              headingId="research-heading"
            />
            <div className="daily-research-list">
              {digest.research.map((item, index) => (
                <article className="daily-research-card" key={item.id}>
                  <div className="daily-research-index">
                    {String(index + 1).padStart(2, "0")}
                  </div>
                  <div className="daily-research-body">
                    <div className="daily-research-meta">
                      <span>{item.field}</span>
                      <span>{item.source}</span>
                      {item.published && <span>{item.published}</span>}
                    </div>
                    <h3>{item.title}</h3>
                    <div className="daily-research-summary">
                      <div>
                        <strong>Problem</strong>
                        <p>{item.problem}</p>
                      </div>
                      <div>
                        <strong>Main idea</strong>
                        <p>{item.mainIdea}</p>
                      </div>
                      <div>
                        <strong>Result</strong>
                        <p>{item.result}</p>
                      </div>
                      <div className="daily-research-why">
                        <strong>Why it matters</strong>
                        <p>{item.whyItMatters}</p>
                      </div>
                    </div>
                    <SourceLink href={item.url}>Read the source</SourceLink>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <DailyMathPractice />

          <section className="daily-section" aria-labelledby="cars-heading">
            <SectionHeading
              eyebrow="Automotive notebook"
              title="Cars worth knowing"
              note="Up to three models, with the context that made them important."
              headingId="cars-heading"
            />
            <div className="daily-car-grid">
              {digest.cars.map((car, index) => (
                <article className="daily-car-card" key={car.name}>
                  {car.imageUrl && (
                    <figure className="daily-car-image">
                      <a
                        href={car.imageSourceUrl || car.imageUrl}
                        target="_blank"
                        rel="noreferrer"
                        aria-label={`Open the image source for ${car.name}`}
                      >
                        <img
                          src={car.imageUrl}
                          alt={car.imageAlt || `${car.name} car`}
                          loading="lazy"
                          decoding="async"
                        />
                      </a>
                      <figcaption>Image via Wikipedia</figcaption>
                    </figure>
                  )}
                  <span className="daily-car-number">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <div className="daily-car-meta">
                    <span>{car.years}</span>
                    <span>{car.country}</span>
                  </div>
                  <h3>{car.name}</h3>
                  <p className="daily-car-category">{car.category}</p>
                  <ul>
                    {car.notes.map((note) => (
                      <li key={note}>{note}</li>
                    ))}
                  </ul>
                  <div className="daily-car-why">
                    <strong>Why it matters</strong>
                    <p>{car.whyItMatters}</p>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section
            className="daily-section daily-poetry-section"
            aria-labelledby="poetry-heading"
          >
            <div className="daily-poetry-card">
              <div className="daily-poetry-intro">
                <span className="daily-kicker">Memory practice</span>
                <h2 id="poetry-heading">{digest.poem.title}</h2>
                <p>{digest.poem.author}</p>
                <div className="daily-poetry-note">
                  <strong>Memory cue</strong>
                  <span>{digest.poem.memoryNote}</span>
                </div>
              </div>
              <blockquote lang="ru">{digest.poem.text}</blockquote>
            </div>
          </section>

          <DailyTimers />

          <footer className="daily-footer">
            <div>
              <span>Sources checked</span>
              <div className="daily-source-list">
                {digest.sources.map((source) => (
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noreferrer"
                    data-ok={source.ok}
                    key={source.label}
                  >
                    {source.label}
                  </a>
                ))}
              </div>
            </div>
            <Link href="/repeat-sentence/">More practice: Repeat Sentence</Link>
          </footer>
        </>
      )}
    </div>
  );
}
