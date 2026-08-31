from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

from api.daily_math import DailyMathService


def generated_practice(prefix: str = "Alpha") -> dict:
    difficulties = ["warm-up", "core", "stretch"]
    problems = []
    for index, difficulty in enumerate(difficulties):
        problems.append(
            {
                "title": f"{prefix} {difficulty}",
                "difficulty": difficulty,
                "concepts": [f"concept {index}"],
                "statement": (
                    f"Compute the value in this original {difficulty} exercise "
                    f"when $x={index + 2}$, and justify the result clearly."
                ),
                "hint": "Start by substituting the given value into the expression.",
                "solutionSteps": [
                    {
                        "label": "Substitute",
                        "explanation": (
                            f"Insert $x={index + 2}$ into the given expression."
                        ),
                    },
                    {
                        "label": "Simplify",
                        "explanation": "Carry out the arithmetic and check the result.",
                    },
                ],
                "finalAnswer": f"$x={index + 2}$",
                "pythonSolution": "",
                "followUp": {
                    "statement": (
                        f"Repeat the same reasoning with $x={index + 3}$ and "
                        "state the resulting value."
                    ),
                    "solutionSteps": [
                        {
                            "label": "Transfer",
                            "explanation": (
                                f"Substitute the modified value $x={index + 3}$."
                            ),
                        }
                    ],
                    "finalAnswer": f"$x={index + 3}$",
                    "pythonSolution": "",
                },
                "sourceConnection": (
                    "This applies the substitution and verification pattern "
                    "developed in the source chapter."
                ),
            }
        )
    return {"problems": problems}


def source(subject_id: str, filename: str) -> dict:
    return {
        "id": subject_id,
        "title": subject_id.replace("-", " ").title(),
        "language": "en",
        "sourceTitle": f"Source for {subject_id}",
        "authors": "Test Author",
        "sourceUrl": "https://example.com/book",
        "availability": "Full open book",
        "license": "Test license",
        "files": [
            {
                "url": "https://example.com/book.pdf",
                "filename": filename,
                "kind": "pdf",
            }
        ],
        "topics": ["substitution", "verification"],
    }


class DailyMathServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.data_file = root / "math_daily.json"
        self.manifest_file = root / "math_sources.json"
        self.resources_dir = root / "sources"
        self.resources_dir.mkdir()
        self.manifest = [
            source("subject-a", "subject-a.pdf"),
            source("subject-b", "subject-b.pdf"),
        ]
        self.manifest_file.write_text(
            json.dumps(self.manifest),
            encoding="utf-8",
        )
        for entry in self.manifest:
            filename = entry["files"][0]["filename"]
            (self.resources_dir / f"{filename}.txt").write_text(
                (
                    "Chapter 1\nExercises\nA complete source excerpt for practice. "
                    "This additional educational context makes the local index long "
                    "enough to qualify as a usable cached source."
                ),
                encoding="utf-8",
            )
        self.generator = AsyncMock(return_value=generated_practice())
        self.service = DailyMathService(
            data_file=self.data_file,
            manifest_file=self.manifest_file,
            resources_dir=self.resources_dir,
            timezone_name="UTC",
            json_generator=self.generator,
        )
        self.service._local_today = lambda: date(2026, 7, 24)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    async def test_generates_three_problems_per_subject_then_uses_cache(self) -> None:
        first = await self.service.get()
        second = await self.service.get()

        self.assertEqual(first.digest.date, "2026-07-24")
        self.assertEqual(len(first.digest.subjects), 2)
        self.assertTrue(
            all(len(subject.problems) == 3 for subject in first.digest.subjects)
        )
        self.assertEqual(self.generator.await_count, 2)
        self.assertEqual(
            second.digest.subjects[0].problems[0].title,
            "Alpha warm-up",
        )
        persisted = json.loads(self.data_file.read_text(encoding="utf-8"))
        self.assertEqual(len(persisted["history"]["subject-a"]), 3)
        self.assertEqual(
            persisted["current"]["sourceRevision"],
            self.service.source_revision,
        )
        self.assertTrue(
            persisted["current"]["subjects"][0]["source"]["locallyCached"]
        )
        self.assertTrue(
            all(
                not problem.solutionOpened
                for subject in first.digest.subjects
                for problem in subject.problems
            )
        )

    async def test_marks_solution_opened_durably_and_idempotently(self) -> None:
        response = await self.service.get()
        problem = response.digest.subjects[0].problems[0]

        first = await self.service.mark_solution_opened(problem.id)
        second = await self.service.mark_solution_opened(problem.id)

        self.assertTrue(first.solutionOpened)
        self.assertEqual(second.solutionOpenedAt, first.solutionOpenedAt)
        reloaded = await self.service.get()
        saved_problem = reloaded.digest.subjects[0].problems[0]
        self.assertTrue(saved_problem.solutionOpened)
        self.assertEqual(saved_problem.solutionOpenedAt, first.solutionOpenedAt)
        persisted = json.loads(self.data_file.read_text(encoding="utf-8"))
        self.assertTrue(
            persisted["current"]["subjects"][0]["problems"][0][
                "solutionOpened"
            ]
        )

    async def test_reuses_only_unopened_problems_on_the_next_day(self) -> None:
        first = await self.service.get()
        subject_a = first.digest.subjects[0]
        subject_b = first.digest.subjects[1]
        await self.service.mark_solution_opened(subject_a.problems[0].id)
        self.generator.reset_mock()
        self.generator.return_value = generated_practice("Beta")
        self.service._local_today = lambda: date(2026, 7, 25)

        second = await self.service.get(wait_for_refresh=True)

        refreshed_a = second.digest.subjects[0]
        carried_b = second.digest.subjects[1]
        self.assertEqual(second.digest.date, "2026-07-25")
        self.assertEqual(self.generator.await_count, 1)
        self.assertEqual(refreshed_a.problems[0].title, "Beta warm-up")
        self.assertNotEqual(
            refreshed_a.problems[0].id,
            subject_a.problems[0].id,
        )
        self.assertEqual(
            [problem.id for problem in refreshed_a.problems[1:]],
            [problem.id for problem in subject_a.problems[1:]],
        )
        self.assertEqual(
            [problem.id for problem in carried_b.problems],
            [problem.id for problem in subject_b.problems],
        )

    async def test_skips_generation_when_every_problem_is_unopened(self) -> None:
        first = await self.service.get()
        original_ids = [
            problem.id
            for subject in first.digest.subjects
            for problem in subject.problems
        ]
        self.generator.reset_mock()
        self.service._local_today = lambda: date(2026, 7, 25)

        second = await self.service.get(wait_for_refresh=True)

        carried_ids = [
            problem.id
            for subject in second.digest.subjects
            for problem in subject.problems
        ]
        self.assertEqual(second.digest.date, "2026-07-25")
        self.assertEqual(carried_ids, original_ids)
        self.generator.assert_not_awaited()

    async def test_rejects_unknown_solution_problem_id(self) -> None:
        await self.service.get()

        with self.assertRaises(KeyError):
            await self.service.mark_solution_opened("unknown-problem")

    async def test_retries_a_problem_key_found_in_persistent_history(self) -> None:
        self.manifest_file.write_text(
            json.dumps([self.manifest[0]]),
            encoding="utf-8",
        )
        self.generator = AsyncMock(
            side_effect=[generated_practice("Alpha"), generated_practice("Beta")]
        )
        self.service = DailyMathService(
            data_file=self.data_file,
            manifest_file=self.manifest_file,
            resources_dir=self.resources_dir,
            timezone_name="UTC",
            json_generator=self.generator,
        )
        self.service._local_today = lambda: date(2026, 7, 24)
        self.data_file.write_text(
            json.dumps(
                {
                    "current": None,
                    "pending": None,
                    "history": {
                        "subject-a": ["alpha warm-up | concept 0"],
                    },
                }
            ),
            encoding="utf-8",
        )

        response = await self.service.get()

        self.assertEqual(
            response.digest.subjects[0].problems[0].title,
            "Beta warm-up",
        )
        self.assertEqual(self.generator.await_count, 2)

    async def test_serves_saved_set_if_forced_refresh_fails(self) -> None:
        first = await self.service.get()
        self.assertFalse(first.stale)
        for subject in first.digest.subjects:
            for problem in subject.problems:
                await self.service.mark_solution_opened(problem.id)
        self.service._local_today = lambda: date(2026, 7, 25)
        self.generator.side_effect = RuntimeError("provider unavailable")

        response = await self.service.get(wait_for_refresh=True)

        self.assertTrue(response.stale)
        self.assertEqual(response.digest.date, "2026-07-24")
        self.assertIn("latest saved set", response.warning)

    async def test_prompt_uses_cached_full_source_text_and_high_reasoning(self) -> None:
        await self.service.get()

        first_call = self.generator.await_args_list[0]
        prompt = first_call.kwargs["messages"][1]["content"]
        self.assertIn("A complete source excerpt for practice.", prompt)
        self.assertEqual(first_call.kwargs["reasoning_effort"], "high")
        self.assertEqual(first_call.kwargs["verbosity"], "high")

    async def test_manifest_revision_invalidates_same_day_cache(self) -> None:
        self.manifest_file.write_text(
            json.dumps([self.manifest[0]]),
            encoding="utf-8",
        )
        first_generator = AsyncMock(return_value=generated_practice("Alpha"))
        first_service = DailyMathService(
            data_file=self.data_file,
            manifest_file=self.manifest_file,
            resources_dir=self.resources_dir,
            timezone_name="UTC",
            json_generator=first_generator,
        )
        first_service._local_today = lambda: date(2026, 7, 24)
        first = await first_service.get()

        changed_manifest = [dict(self.manifest[0])]
        changed_manifest[0]["topics"] = ["new source edition"]
        self.manifest_file.write_text(
            json.dumps(changed_manifest),
            encoding="utf-8",
        )
        second_generator = AsyncMock(return_value=generated_practice("Beta"))
        second_service = DailyMathService(
            data_file=self.data_file,
            manifest_file=self.manifest_file,
            resources_dir=self.resources_dir,
            timezone_name="UTC",
            json_generator=second_generator,
        )
        second_service._local_today = lambda: date(2026, 7, 24)

        second = await second_service.get()

        self.assertEqual(
            first.digest.subjects[0].problems[0].title,
            "Alpha warm-up",
        )
        self.assertEqual(
            second.digest.subjects[0].problems[0].title,
            "Beta warm-up",
        )
        self.assertNotEqual(first.digest.sourceRevision, second.digest.sourceRevision)
        self.assertEqual(second_generator.await_count, 1)

    async def test_multi_book_subject_uses_one_origin_per_problem(self) -> None:
        multi_source = source("mathematical-analysis", "book-one.pdf")
        multi_source["sourceTitle"] = "Three analysis books"
        multi_source["problemSourcePolicy"] = "one_problem_per_source"
        multi_source["problemSources"] = [
            {
                "title": "Zorich",
                "authors": "V. A. Zorich",
                "sourceUrl": "https://example.com/zorich",
                "edition": "2021",
                "materialNote": "Full text.",
            },
            {
                "title": "Demidovich",
                "authors": "B. P. Demidovich",
                "sourceUrl": "https://example.com/demidovich",
                "edition": "2022",
                "materialNote": "Full text.",
            },
            {
                "title": "Kaczor and Nowak",
                "authors": "W. J. Kaczor and M. T. Nowak",
                "sourceUrl": "https://example.com/kaczor-nowak",
                "edition": "2000",
                "materialNote": "Official preview.",
            },
        ]
        multi_source["files"] = [
            {
                "url": f"https://example.com/book-{index}.pdf",
                "filename": f"book-{index}.pdf",
                "kind": "pdf",
                "sourceIndex": index,
            }
            for index in range(3)
        ]
        self.manifest_file.write_text(
            json.dumps([multi_source]),
            encoding="utf-8",
        )
        for index in range(3):
            (self.resources_dir / f"book-{index}.pdf.txt").write_text(
                (
                    f"Book {index + 1}\nExercises\nA complete analysis problem "
                    "excerpt with enough explanatory source text for local indexing."
                ),
                encoding="utf-8",
            )
        generator = AsyncMock(return_value=generated_practice())
        service = DailyMathService(
            data_file=self.data_file,
            manifest_file=self.manifest_file,
            resources_dir=self.resources_dir,
            timezone_name="UTC",
            json_generator=generator,
        )
        service._local_today = lambda: date(2026, 7, 24)

        response = await service.get()

        self.assertEqual(
            [problem.sourceTitle for problem in response.digest.subjects[0].problems],
            ["Zorich", "Demidovich", "Kaczor and Nowak"],
        )
        prompt = generator.await_args.kwargs["messages"][1]["content"]
        self.assertIn('<book_reference index="1">', prompt)
        self.assertIn('<book_reference index="2">', prompt)
        self.assertIn('<book_reference index="3">', prompt)
        self.assertIn("Problem 1 (warm-up) must come from book_reference 1", prompt)

if __name__ == "__main__":
    unittest.main()
