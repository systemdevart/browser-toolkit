"use client";

import katex from "katex";
import { useCallback, useEffect, useMemo, useState } from "react";

function MathText({ children }) {
  const parts = useMemo(
    () => String(children || "").split(/(\$\$[\s\S]+?\$\$|\$[^$\n]+?\$)/g),
    [children]
  );

  return (
    <span className="math-text">
      {parts.map((part, index) => {
        const display = part.startsWith("$$") && part.endsWith("$$");
        const inline = !display && part.startsWith("$") && part.endsWith("$");
        if (!display && !inline) {
          return <span key={`${index}-${part.slice(0, 12)}`}>{part}</span>;
        }
        const source = part.slice(display ? 2 : 1, display ? -2 : -1);
        const rendered = katex.renderToString(source, {
          displayMode: display,
          throwOnError: false,
          strict: "warn",
          trust: false,
        });
        return (
          <span
            className={display ? "math-display" : "math-inline"}
            dangerouslySetInnerHTML={{ __html: rendered }}
            key={`${index}-${source.slice(0, 12)}`}
          />
        );
      })}
    </span>
  );
}

async function responseError(response) {
  try {
    const payload = await response.json();
    if (typeof payload?.detail === "string") return payload.detail;
  } catch {
    // Use the status fallback.
  }
  return `Request failed (${response.status})`;
}

function Solution({ steps, finalAnswer, pythonSolution }) {
  return (
    <div className="math-solution">
      <ol>
        {steps.map((step, index) => (
          <li key={`${step.label}-${index}`}>
            <strong>{step.label}</strong>
            <MathText>{step.explanation}</MathText>
          </li>
        ))}
      </ol>
      <div className="math-final-answer">
        <span className="math-final-label">Answer</span>
        <MathText>{finalAnswer}</MathText>
      </div>
      {pythonSolution && (
        <div className="math-python-solution">
          <div>
            <span>Python 3 solution</span>
            <span>Runnable reference</span>
          </div>
          <pre>
            <code>{pythonSolution}</code>
          </pre>
        </div>
      )}
    </div>
  );
}

function ProblemCard({ problem, index, onSolutionOpened }) {
  const [trackingState, setTrackingState] = useState("idle");
  const [trackingError, setTrackingError] = useState("");
  const solutionOpened = problem.solutionOpened || trackingState === "saved";

  const recordSolutionOpened = useCallback(async () => {
    if (solutionOpened || trackingState === "saving") return;
    setTrackingState("saving");
    setTrackingError("");
    try {
      await onSolutionOpened(problem.id);
      setTrackingState("saved");
    } catch (saveError) {
      setTrackingState("error");
      setTrackingError(
        saveError.message || "The solution view could not be saved."
      );
    }
  }, [onSolutionOpened, problem.id, solutionOpened, trackingState]);

  return (
    <article className="math-problem-card">
      <div className="math-problem-topline">
        <span className="math-problem-number">
          {String(index + 1).padStart(2, "0")}
        </span>
        <span
          className={`math-difficulty math-difficulty-${problem.difficulty}`}
        >
          {problem.difficulty}
        </span>
      </div>
      <h3>
        <MathText>{problem.title}</MathText>
      </h3>
      <a
        className="math-problem-source"
        href={problem.sourceUrl}
        target="_blank"
        rel="noreferrer"
      >
        Source book
        <span>{problem.sourceTitle}</span>
        <span aria-hidden="true">↗</span>
      </a>
      <div className="math-concepts">
        {problem.concepts.map((concept) => (
          <span key={concept}>
            <MathText>{concept}</MathText>
          </span>
        ))}
      </div>
      <div className="math-statement">
        <MathText>{problem.statement}</MathText>
      </div>

      <div
        className="math-solution-state"
        data-opened={solutionOpened}
        role="status"
      >
        <span aria-hidden="true" />
        <div>
          <strong>
            {solutionOpened
              ? "Solution opened"
              : trackingState === "saving"
                ? "Saving solution view"
                : "Solution not opened"}
          </strong>
          <p>
            {solutionOpened
              ? "Counted as solved; a new problem can replace it tomorrow."
              : trackingState === "error"
                ? trackingError
                : "Not counted as solved; this problem will remain eligible for tomorrow."}
          </p>
        </div>
        {trackingState === "error" && !solutionOpened && (
          <button type="button" onClick={() => void recordSolutionOpened()}>
            Retry
          </button>
        )}
      </div>

      <details className="math-disclosure math-hint">
        <summary>Show hint</summary>
        <div>
          <MathText>{problem.hint}</MathText>
        </div>
      </details>

      <details
        className="math-disclosure"
        onToggle={(event) => {
          if (event.currentTarget.open) void recordSolutionOpened();
        }}
      >
        <summary>Open worked solution</summary>
        <Solution
          steps={problem.solutionSteps}
          finalAnswer={problem.finalAnswer}
          pythonSolution={problem.pythonSolution}
        />
      </details>

      <details className="math-disclosure math-follow-up">
        <summary>Try the follow-up</summary>
        <div className="math-follow-up-body">
          <div className="math-follow-up-statement">
            <MathText>{problem.followUp.statement}</MathText>
          </div>
          <details className="math-disclosure math-nested-solution">
            <summary>Open follow-up solution</summary>
            <Solution
              steps={problem.followUp.solutionSteps}
              finalAnswer={problem.followUp.finalAnswer}
              pythonSolution={problem.followUp.pythonSolution}
            />
          </details>
        </div>
      </details>

      <p className="math-source-connection">
        <strong>Source connection</strong>
        <MathText>{problem.sourceConnection}</MathText>
      </p>
    </article>
  );
}

export default function DailyMathPractice() {
  const [payload, setPayload] = useState(null);
  const [activeSubjectId, setActiveSubjectId] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError("");
    try {
      const response = await fetch("/api/daily/math", { cache: "no-store" });
      if (!response.ok) throw new Error(await responseError(response));
      const next = await response.json();
      setPayload(next);
      setActiveSubjectId((current) => {
        const stillExists = next.digest.subjects.some(
          (subject) => subject.subjectId === current
        );
        return stillExists ? current : next.digest.subjects[0]?.subjectId || "";
      });
    } catch (loadError) {
      setError(loadError.message || "Could not load today's problem set.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const interval = window.setInterval(() => void load(), 5 * 60 * 1000);
    return () => window.clearInterval(interval);
  }, [load]);

  const subjects = payload?.digest?.subjects || [];
  const active =
    subjects.find((subject) => subject.subjectId === activeSubjectId) ||
    subjects[0];
  const problemCount = subjects.reduce(
    (total, subject) => total + subject.problems.length,
    0
  );
  const recordSolutionOpened = useCallback(async (problemId) => {
    const response = await fetch(
      `/api/daily/math/problems/${encodeURIComponent(problemId)}/solution-opened`,
      {
        method: "POST",
        cache: "no-store",
        keepalive: true,
      }
    );
    if (!response.ok) throw new Error(await responseError(response));
    const saved = await response.json();
    setPayload((current) => {
      if (!current?.digest?.subjects) return current;
      return {
        ...current,
        digest: {
          ...current.digest,
          subjects: current.digest.subjects.map((subject) => ({
            ...subject,
            problems: subject.problems.map((problem) =>
              problem.id === saved.problemId
                ? {
                    ...problem,
                    solutionOpened: true,
                    solutionOpenedAt: saved.solutionOpenedAt,
                  }
                : problem
            ),
          })),
        },
      };
    });
  }, []);

  return (
    <section
      className="daily-section daily-math-section"
      aria-labelledby="math-heading"
    >
      <div className="daily-section-heading">
        <div>
          <span>Daily problem studio</span>
          <h2 id="math-heading">Mathematics and ML practice</h2>
        </div>
        <p>
          {subjects.length
            ? `${problemCount} source-based problems across ${subjects.length} subjects, each with a worked transfer exercise.`
            : "Three sourced problems per subject, with hints and worked follow-ups."}
        </p>
      </div>

      {loading && !active && (
        <div className="math-loading" role="status" aria-live="polite">
          <span className="math-loading-orbit" aria-hidden="true" />
          <div>
            <strong>Preparing today's problem set</strong>
            <p>
              The first edition reads the full source library and may take a few
              minutes. Future visits use the saved daily set.
            </p>
          </div>
        </div>
      )}

      {error && !active && (
        <div className="math-error" role="alert">
          <strong>Problem studio is temporarily unavailable.</strong>
          <p>{error}</p>
          <button type="button" onClick={() => void load()}>
            Try again
          </button>
        </div>
      )}

      {payload?.warning && (
        <div className="math-warning" role="status">
          {payload.warning}
        </div>
      )}

      {active && (
        <>
          <div
            className="math-subject-tabs"
            role="tablist"
            aria-label="Math practice subjects"
          >
            {subjects.map((subject, index) => (
              <button
                type="button"
                role="tab"
                aria-selected={subject.subjectId === active.subjectId}
                aria-controls={`math-panel-${subject.subjectId}`}
                id={`math-tab-${subject.subjectId}`}
                onClick={() => setActiveSubjectId(subject.subjectId)}
                key={subject.subjectId}
              >
                <span>{String(index + 1).padStart(2, "0")}</span>
                {subject.title}
              </button>
            ))}
          </div>

          <div
            className="math-subject-panel"
            role="tabpanel"
            id={`math-panel-${active.subjectId}`}
            aria-labelledby={`math-tab-${active.subjectId}`}
            lang={active.language}
          >
            <div className="math-subject-header">
              <div>
                <span>Today's source</span>
                <h3>{active.source.title}</h3>
                <p>{active.source.authors}</p>
              </div>
              <div className="math-source-status">
                <span data-cached={active.source.locallyCached}>
                  {active.source.locallyCached
                    ? "Source cache ready"
                    : "Source outline"}
                </span>
                <a href={active.source.url} target="_blank" rel="noreferrer">
                  Open source <span aria-hidden="true">↗</span>
                </a>
              </div>
            </div>
            <p className="math-source-note">
              {active.source.availability}. {active.source.license}.
            </p>

            <div className="math-problem-list">
              {active.problems.map((problem, index) => (
                <ProblemCard
                  problem={problem}
                  index={index}
                  onSolutionOpened={recordSolutionOpened}
                  key={problem.id}
                />
              ))}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
