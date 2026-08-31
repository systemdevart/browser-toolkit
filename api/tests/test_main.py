from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


API_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))

import main  # noqa: E402


def writing_topic_result(**overrides):
    result = {
        "title": "Public transport",
        "prompt": (
            "The visual shows changes in public transport use. Summarise the main "
            "features and make comparisons where relevant."
        ),
        "questionType": "Academic Writing Task 1",
        "visualType": "none",
        "visualTitle": "",
        "tableColumns": [],
        "tableRows": [],
        "chartCategories": [],
        "chartSeries": [],
        "processSteps": [],
        "mapBefore": [],
        "mapAfter": [],
        "bulletPoints": [],
        "letterOpening": "",
    }
    result.update(overrides)
    return result


class DailyApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.original_data_file = main.BANS_DATA_FILE
        self.original_timer_service = main.daily_timer_service
        self.original_concept_memory_service = main.concept_memory_service
        self.original_writing_progress_service = main.writing_progress_service
        main.BANS_DATA_FILE = Path(self.temporary_directory.name) / "bans.json"
        main.daily_timer_service = main.DailyTimerService(
            database_file=(
                Path(self.temporary_directory.name) / "daily_timers.sqlite3"
            ),
            timezone_name="UTC",
        )
        main.concept_memory_service = main.ConceptMemoryService(
            database_file=(
                Path(self.temporary_directory.name) / "concept_memory.sqlite3"
            ),
            timezone_name="UTC",
        )
        main.writing_progress_service = main.WritingProgressService(
            database_file=(
                Path(self.temporary_directory.name) / "ielts_writing.sqlite3"
            ),
        )
        main._provider_requests.clear()
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        main.BANS_DATA_FILE = self.original_data_file
        main.daily_timer_service = self.original_timer_service
        main.concept_memory_service = self.original_concept_memory_service
        main.writing_progress_service = self.original_writing_progress_service
        self.temporary_directory.cleanup()

    def test_vocab_ban_lifecycle_remains_compatible(self) -> None:
        self.assertEqual(self.client.get("/api/vocab/bans").json(), {"bans": {}})

        response = self.client.post(
            "/api/vocab/bans/c1-cefr", json={"word": "  Example  "}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "banned": ["example"]})
        self.assertEqual(
            self.client.get("/api/vocab/bans").json(),
            {"bans": {"c1-cefr": ["example"]}},
        )

        response = self.client.delete("/api/vocab/bans/c1-cefr/example")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "banned": []})

    def test_invalid_vocab_source_is_rejected(self) -> None:
        response = self.client.post("/api/vocab/bans/not%20safe", json={"word": "x"})
        self.assertEqual(response.status_code, 400)

    def test_auth_check_rejects_a_missing_session(self) -> None:
        response = self.client.get("/auth/check")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_auth_required_preserves_a_safe_sandbox_destination(self) -> None:
        response = self.client.get(
            "/auth/required",
            headers={
                "X-Original-Host": "sandbox.chebakov.me",
                "X-Original-URI": "/ielts-writing/?mode=essay",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.headers["location"].startswith(
                "https://daily.chebakov.me/auth/login?"
            )
        )
        self.assertIn("sandbox.chebakov.me", response.headers["location"])

    def test_math_generation_uses_the_dedicated_math_model(self) -> None:
        generation = AsyncMock(return_value={"ok": True})
        with patch.object(main, "_openai_json", generation):
            result = asyncio.run(
                main._openai_math_json(
                    messages=[{"role": "user", "content": "Solve this."}],
                    schema_name="math_test",
                    schema={"type": "object"},
                    max_tokens=100,
                    reasoning_effort="high",
                )
            )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(
            generation.await_args.kwargs["model"],
            main.OPENAI_MATH_MODEL,
        )

    def test_daily_timer_start_is_server_enforced(self) -> None:
        initial = self.client.get("/api/daily/timers")
        started = self.client.post("/api/daily/timers/english-reading/start")
        conflict = self.client.post("/api/daily/timers/russian-reading/start")

        self.assertEqual(initial.status_code, 200)
        self.assertEqual(
            [activity["status"] for activity in initial.json()["activities"]],
            ["available", "available"],
        )
        self.assertEqual(started.status_code, 200)
        self.assertEqual(
            started.json()["activities"][0]["status"],
            "running",
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertIn("already running", conflict.json()["detail"])

    def test_concept_memory_create_list_and_delete_lifecycle(self) -> None:
        created = self.client.post(
            "/api/daily/concepts",
            json={
                "concept": "  The spacing effect  ",
                "explanation": (
                    "Reviewing across separate sessions improves durable recall."
                ),
            },
        )

        self.assertEqual(created.status_code, 200)
        concept = created.json()["upcomingConcepts"][0]
        self.assertEqual(concept["concept"], "The spacing effect")
        self.assertEqual(concept["reviewNumber"], 1)
        self.assertEqual(
            self.client.get("/api/daily/concepts").json()["stats"][
                "activeConcepts"
            ],
            1,
        )

        deleted = self.client.delete(f"/api/daily/concepts/{concept['id']}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["stats"]["activeConcepts"], 0)

    def test_concept_memory_rejects_blank_concept(self) -> None:
        response = self.client.post(
            "/api/daily/concepts",
            json={"concept": "   "},
        )

        self.assertEqual(response.status_code, 422)

    def test_due_concept_read_is_immediate_and_question_is_persisted(self) -> None:
        now = [datetime(2026, 8, 9, 9, 0, tzinfo=timezone.utc)]
        main.concept_memory_service = main.ConceptMemoryService(
            database_file=(
                Path(self.temporary_directory.name) / "question_memory.sqlite3"
            ),
            timezone_name="UTC",
            now_provider=lambda: now[0],
        )
        main.concept_memory_service.create(concept="Шумер")
        now[0] = datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc)
        generation = AsyncMock(
            return_value={
                "question": (
                    "Какая древняя цивилизация Южной Месопотамии создала "
                    "одни из первых городов и клинопись?"
                )
            }
        )

        with patch.object(main, "_openai_json", generation):
            first = self.client.get("/api/daily/concepts")
            asyncio.run(main._prepare_concept_questions())
            second = self.client.get("/api/daily/concepts")

        self.assertEqual(first.status_code, 200)
        self.assertIsNone(first.json()["dueConcepts"][0]["question"])
        due = second.json()["dueConcepts"][0]
        self.assertNotIn("Шумер", due["question"])
        self.assertEqual(due["questionDate"], "2026-08-10")
        self.assertEqual(generation.await_count, 1)

    def test_duplicate_active_concept_returns_conflict(self) -> None:
        first = self.client.post(
            "/api/daily/concepts", json={"concept": "Шумер"}
        )
        duplicate = self.client.post(
            "/api/daily/concepts", json={"concept": " шумер "}
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(duplicate.status_code, 409)
        self.assertIn("already", duplicate.json()["detail"])

    def test_recall_question_rejects_direct_concept_mentions(self) -> None:
        self.assertTrue(
            main._question_exposes_concept(
                "Как развивалась шумерская письменность?",
                "Шумер",
            )
        )
        self.assertFalse(
            main._question_exposes_concept(
                "Какая цивилизация создала первые города Южной Месопотамии?",
                "Шумер",
            )
        )

    def test_recall_question_requires_russian(self) -> None:
        self.assertTrue(
            main._question_is_russian(
                "Какая древняя цивилизация создала первые города Месопотамии?"
            )
        )
        self.assertFalse(
            main._question_is_russian(
                "Яка давня цивілізація створила перші міста Месопотамії?"
            )
        )
        self.assertFalse(
            main._question_is_russian(
                "Which ancient civilization created the first Mesopotamian cities?"
            )
        )

    def test_recall_question_uses_plain_quotes(self) -> None:
        self.assertEqual(
            main._normalize_recall_punctuation(
                "Как называли «царя», оставившего “свод законов”?"
            ),
            'Как называли "царя", оставившего "свод законов"?',
        )

    def test_recall_question_retries_non_russian_output(self) -> None:
        generation = AsyncMock(
            side_effect=[
                {"question": "Qual nome tem origem em um antigo antropônimo?"},
                {
                    "question": (
                        "Какое имя происходит от древнего германского антропонима "
                        "со значением правителя дома?"
                    )
                },
            ]
        )
        target = main.ConceptCueTarget(
            id="concept-id",
            concept="Henri Prestes",
            recallDate="2026-08-15",
            previousQuestions=[],
        )

        with patch.object(main, "_openai_json", generation):
            question = asyncio.run(main._generate_concept_question(target))

        self.assertEqual(
            question,
            (
                "Какое имя происходит от древнего германского антропонима "
                "со значением правителя дома?"
            ),
        )
        self.assertEqual(generation.await_count, 2)

    def test_short_topic_discards_accidental_cue_points(self) -> None:
        generated = {
            "title": "Weekends",
            "prompt": "What do you usually enjoy doing at the weekend, and why?",
            "bulletPoints": ["This should be removed"],
        }
        with patch.object(main, "_openai_json", AsyncMock(return_value=generated)):
            response = self.client.post(
                "/api/ielts/topic", json={"mode": "short", "recentTopics": []}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["bulletPoints"], [])

    def test_long_topic_requires_four_cue_points(self) -> None:
        generated = {
            "title": "A useful object",
            "prompt": "Describe a useful object you own.",
            "bulletPoints": ["what it is"],
        }
        with patch.object(main, "_openai_json", AsyncMock(return_value=generated)):
            response = self.client.post(
                "/api/ielts/topic", json={"mode": "long", "recentTopics": []}
            )
        self.assertEqual(response.status_code, 502)

    def test_british_voice_detection_uses_accent_or_verified_locale(self) -> None:
        self.assertTrue(
            main._is_british_voice(
                {"labels": {"accent": "British"}, "verified_languages": []}
            )
        )
        self.assertTrue(
            main._is_british_voice(
                {
                    "labels": {},
                    "verified_languages": [
                        {"language": "en", "locale": "en-GB"}
                    ],
                }
            )
        )
        self.assertFalse(
            main._is_british_voice(
                {"labels": {"accent": "American"}, "verified_languages": []}
            )
        )

    def test_spoken_topic_endpoint_returns_elevenlabs_audio(self) -> None:
        topic = {
            "id": "spoken-topic",
            "mode": "long",
            "title": "A useful object",
            "prompt": "Describe a useful object you own.",
            "bulletPoints": [
                "what it is",
                "when you got it",
                "how you use it",
                "why it is useful",
            ],
        }
        synthesis = AsyncMock(
            return_value=(b"ID3\x04\x00\x00test-audio", "Alice - British")
        )

        with patch.object(main, "_elevenlabs_british_speech", synthesis):
            response = self.client.post("/api/ielts/topic/audio", json=topic)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/mpeg")
        self.assertEqual(
            response.headers["x-elevenlabs-voice"],
            "Alice - British",
        )
        self.assertEqual(response.content, b"ID3\x04\x00\x00test-audio")
        spoken_topic = synthesis.await_args.args[0]
        self.assertIn(
            "You should say: what it is. when you got it",
            main._topic_speech_text(spoken_topic),
        )

    def test_speaking_evaluation_returns_minimal_band_75_rewrite(self) -> None:
        delivery = {
            "pronunciation": {
                "band": 7.0,
                "feedback": "The response is easy to understand.",
            },
            "naturalness": {
                "band": 7.0,
                "feedback": "The delivery is mostly natural.",
            },
            "rhythmAndStress": {
                "band": 7.0,
                "feedback": "Stress generally supports the meaning.",
            },
            "intelligibility": {
                "band": 7.5,
                "feedback": "The recording is consistently clear.",
            },
            "summary": "A clear response with mostly natural delivery.",
        }
        generated = {
            "overallBand": 6.5,
            "summary": "A relevant answer with a few grammatical errors.",
            "criteria": {
                "fluencyAndCoherence": {
                    "band": 7.0,
                    "feedback": "The answer develops one clear idea.",
                },
                "lexicalResource": {
                    "band": 6.5,
                    "feedback": "The vocabulary is sufficient for the topic.",
                },
                "grammaticalRangeAndAccuracy": {
                    "band": 6.0,
                    "feedback": "Verb forms need more control.",
                },
                "pronunciation": delivery["pronunciation"],
            },
            "deliveryAssessment": delivery,
            "strengths": ["The reason is clear and relevant."],
            "grammarCorrections": [
                {
                    "original": "I like read books",
                    "correction": "I like reading books",
                    "explanation": "Use a gerund after like.",
                }
            ],
            "suggestions": ["Control verb forms more consistently."],
            "targetStatus": "close",
            "targetFocus": "Improve verb-form accuracy.",
            "rewrittenResponse": (
                "I like reading books because they help me relax."
            ),
        }
        generator = AsyncMock(return_value=generated)
        payload = {
            "topic": {
                "id": "speaking-topic",
                "mode": "short",
                "title": "Reading",
                "prompt": "Do you enjoy reading books, and why?",
                "bulletPoints": [],
            },
            "transcript": "I like read books because it help me relax.",
            "stats": {
                "recordedSeconds": 8.0,
                "speechSeconds": 8.0,
                "wordCount": 9,
                "wordsPerMinute": 68,
                "pauseCount": 0,
                "longPauseCount": 0,
            },
            "audioAssessment": delivery,
        }

        with patch.object(main, "_openai_json", generator):
            response = self.client.post("/api/ielts/evaluate", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["rewrittenResponse"],
            "I like reading books because they help me relax.",
        )
        system_prompt = generator.await_args.kwargs["messages"][0]["content"]
        self.assertIn("smallest possible number of changes", system_prompt)
        self.assertIn("Preserve their ideas", system_prompt)

    def test_writing_essay_discards_visual_data(self) -> None:
        generated = writing_topic_result(
            title="Working from home",
            prompt=(
                "Some people believe working from home benefits both employees and "
                "employers. To what extent do you agree or disagree?"
            ),
            questionType="Opinion",
            visualType="table",
            visualTitle="This should be removed",
            tableColumns=["A", "B", "C"],
            tableRows=[["1", "2", "3"]] * 3,
        )
        with patch.object(main, "_openai_json", AsyncMock(return_value=generated)):
            response = self.client.post(
                "/api/ielts/writing/topic",
                json={"mode": "essay_opinion", "recentTopics": []},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tableRows"], [])

    def test_letter_topic_separates_fixed_instructions_and_salutation(self) -> None:
        generated = writing_topic_result(
            title="Request to change a volunteering schedule",
            prompt=(
                "You should spend about 20 minutes on this task. You volunteer "
                "regularly at a local community centre. A change in your personal "
                "circumstances means that you can no longer work at your usual time. "
                "Write a letter to the manager of the community centre. In your "
                "letter: • explain why you need to change your volunteering schedule "
                "• suggest alternative days or times when you could volunteer "
                "• ask whether there are any other duties you could perform. Write "
                "at least 150 words. You do NOT need to write any addresses. Begin "
                "your letter as follows: Dear Ms Patel,"
            ),
            questionType="General Training Task 1 - semi-formal letter",
            visualType="letter",
            visualTitle="Community centre manager",
            bulletPoints=[
                "Explain why you need to change your volunteering schedule.",
                "Suggest alternative days or times when you could volunteer.",
                "Ask whether there are any other duties you could perform.",
            ],
            letterOpening="",
        )

        with patch.object(main, "_openai_json", AsyncMock(return_value=generated)):
            response = self.client.post(
                "/api/ielts/writing/topic",
                json={
                    "mode": "general_semiformal_letter",
                    "recentTopics": [],
                },
            )

        self.assertEqual(response.status_code, 200)
        topic = response.json()
        self.assertEqual(
            topic["prompt"],
            (
                "You volunteer regularly at a local community centre. A change in "
                "your personal circumstances means that you can no longer work at "
                "your usual time. Write a letter to the manager of the community "
                "centre."
            ),
        )
        self.assertNotIn("150 words", topic["prompt"])
        self.assertNotIn("explain why", topic["prompt"].lower())
        self.assertEqual(topic["letterOpening"], "Dear Ms Patel,")
        self.assertEqual(len(topic["bulletPoints"]), 3)

    def test_writing_task_one_requires_rectangular_table(self) -> None:
        generated = writing_topic_result(
            title="Transport use",
            prompt=(
                "The table shows transport use. Summarise the main features and "
                "make comparisons where relevant."
            ),
            questionType="Academic table report",
            visualType="table",
            visualTitle="Journeys by mode (%)",
            tableColumns=["Mode", "2000", "2025"],
            tableRows=[
                ["Car", "50", "40"],
                ["Bus", "20"],
                ["Rail", "30", "40"],
            ],
        )
        with patch.object(main, "_openai_json", AsyncMock(return_value=generated)):
            response = self.client.post(
                "/api/ielts/writing/topic",
                json={"mode": "academic_table", "recentTopics": []},
            )
        self.assertEqual(response.status_code, 502)

    def test_writing_evaluation_uses_server_word_count(self) -> None:
        generated = {
            "overallBand": 7.5,
            "summary": "A clear and well-developed response.",
            "criteria": {
                "taskAchievementOrResponse": {
                    "band": 8,
                    "feedback": "The position is clear.",
                },
                "coherenceAndCohesion": {
                    "band": 7,
                    "feedback": "Paragraphing is logical.",
                },
                "lexicalResource": {
                    "band": 7.5,
                    "feedback": "Vocabulary is flexible.",
                },
                "grammaticalRangeAndAccuracy": {
                    "band": 7,
                    "feedback": "Complex structures are mostly accurate.",
                },
            },
            "strengths": ["Clear position"],
            "grammarCorrections": [],
            "suggestions": ["Develop the second example further."],
            "structureFeedback": "The introduction and body paragraphs are clear.",
            "targetStatus": "on track",
            "targetFocus": "Improve precision in supporting examples.",
            "wordCount": 999,
            "rewrittenEssay": (
                "Public transport should be free for everyone because it would "
                "improve access and reduce congestion."
            ),
        }
        topic = {
            "id": "test-topic",
            "mode": "essay_opinion",
            "title": "Public transport",
            "prompt": "Should cities make public transport free? Discuss.",
            "questionType": "Opinion",
            "visualType": "none",
            "visualTitle": "",
            "tableColumns": [],
            "tableRows": [],
            "chartCategories": [],
            "chartSeries": [],
            "processSteps": [],
            "mapBefore": [],
            "mapAfter": [],
            "bulletPoints": [],
        }
        with patch.object(main, "_openai_json", AsyncMock(return_value=generated)):
            response = self.client.post(
                "/api/ielts/writing/evaluate",
                json={
                    "topic": topic,
                    "essay": "Public transport should be free for everyone.",
                    "elapsedSeconds": 300,
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["wordCount"], 7)
        self.assertTrue(response.json()["attemptId"].startswith("writing-"))
        self.assertEqual(len(main.writing_progress_service.summaries()), 1)

    def test_delivery_stats_use_transcript_and_recording_duration(self) -> None:
        stats = main._calculate_delivery_stats(
            "I enjoy reading because it helps me relax.",
            5.0,
        )
        self.assertEqual(stats["wordCount"], 8)
        self.assertEqual(stats["wordsPerMinute"], 96)
        self.assertEqual(stats["recordedSeconds"], 5.0)

    def test_transcription_rejects_non_audio_body_before_provider_call(self) -> None:
        with patch.object(main, "OPENAI_API_KEY", "test-key"):
            response = self.client.post(
                "/api/ielts/transcribe",
                content=b"not audio" * 100,
                headers={"Content-Type": "text/plain"},
            )
        self.assertEqual(response.status_code, 415)

    def test_transcription_combines_text_and_audio_delivery(self) -> None:
        audio_assessment = main.AudioDeliveryAssessment.model_validate(
            {
                "pronunciation": {"band": 7.5, "feedback": "Clear articulation."},
                "naturalness": {"band": 7, "feedback": "Mostly natural pacing."},
                "rhythmAndStress": {
                    "band": 7,
                    "feedback": "Key words usually receive stress.",
                },
                "intelligibility": {
                    "band": 8,
                    "feedback": "Easy to understand.",
                },
                "summary": "Clear, natural, and intelligible overall.",
            }
        )
        with (
            patch.object(main, "OPENAI_API_KEY", "test-key"),
            patch.object(
                main,
                "_openai_transcribe",
                AsyncMock(return_value="I enjoy learning languages."),
            ),
            patch.object(
                main,
                "_openai_audio_assessment",
                AsyncMock(return_value=audio_assessment),
            ),
        ):
            response = self.client.post(
                "/api/ielts/transcribe",
                content=b"RIFF" + b"\0" * 512,
                headers={
                    "Content-Type": "audio/wav",
                    "X-Recording-Duration-Ms": "5000",
                },
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["transcript"], "I enjoy learning languages.")
        self.assertEqual(payload["audioAssessment"]["pronunciation"]["band"], 7.5)
        self.assertEqual(payload["stats"]["wordCount"], 4)

    def test_provider_rate_limit_returns_retry_after(self) -> None:
        request = type(
            "RequestStub",
            (),
            {"headers": {"x-real-ip": "192.0.2.1"}, "client": None},
        )()
        main._enforce_provider_rate_limit(request, "test", limit=1)
        with self.assertRaises(main.HTTPException) as raised:
            main._enforce_provider_rate_limit(request, "test", limit=1)
        self.assertEqual(raised.exception.status_code, 429)
        self.assertIn("Retry-After", raised.exception.headers)


if __name__ == "__main__":
    unittest.main()
