import VocabQuiz from "@/components/VocabQuiz";
import Link from "next/link";

export const metadata = {
  title: "Vocab quiz · daily.chebakov.me",
};

export default function VocabPage() {
  return (
    <div className="page-shell">
      <main className="page-main">
        <header className="site-header">
          <h1 className="site-title">Vocab quiz</h1>
          <p className="site-subtitle">English and French → Russian</p>
        </header>
        <VocabQuiz />
        <Link className="back-link" href="/">
          ← back to daily.chebakov.me
        </Link>
      </main>
    </div>
  );
}
