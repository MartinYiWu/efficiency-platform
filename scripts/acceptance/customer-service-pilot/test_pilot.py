import importlib.util
import unittest
from pathlib import Path

import httpx

spec = importlib.util.spec_from_file_location("pilot", Path(__file__).with_name("pilot.py"))
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


class PilotTest(unittest.TestCase):
    def test_paginated_exact_scope_and_dedup(self):
        calls = []
        def handle(request):
            calls.append(str(request.url))
            if request.url.path.endswith("feedback"):
                page = int(request.url.params["page"])
                items = [{"id": "f1", "runId": "r1"}, {"id": "other", "runId": "r2"}] if page == 1 else [{"id": "f1", "runId": "r1"}, {"id": "f2", "runId": "r1"}]
                return httpx.Response(200, json={"code": "SUCCESS", "data": {"items": items, "total": 4}})
            return httpx.Response(200, json={"data": {"run": {"id": "r1", "agentReleaseId": "release"}, "citations": []}})
        client = httpx.Client(transport=httpx.MockTransport(handle), base_url="http://test")
        result = pilot.collect(client, ["r1", "r1"], ["f1", "f2"], 2)
        self.assertEqual([f["id"] for f in result["feedback"]], ["f1", "f2"])
        self.assertEqual(len(result["replays"]), 1)
        self.assertEqual(len(calls), 3)

    def test_report_excludes_sensitive_content_and_does_not_invent_ttft(self):
        raw = {"cohort": "developer", "feedback": [{"id": "f", "runId": "r", "comment": "secret", "userId": "person"}], "replays": [{"run": {"id": "r", "agentReleaseId": "v", "startedAt": "2026-01-01T00:00:00Z", "finishedAt": "2026-01-01T00:00:02Z"}, "question": {"content": "private"}, "stages": [{"internalPayload": "token"}], "citations": []}]}
        report = pilot.review(raw)
        self.assertEqual(report["items"][0]["totalDurationMs"], 2000)
        self.assertIsNone(report["items"][0]["ttftMs"])
        self.assertEqual(report["confirmedEmployeeCount"], 0)
        self.assertNotIn("secret", str(report))
        self.assertNotIn("private", str(report))
        self.assertNotIn("person", str(report))

    def test_export_requires_human_review_and_frozen_source(self):
        raw = {"cohort": "developer", "feedback": [], "replays": [{"run": {"id": "r", "agentReleaseId": "release"}, "citations": [{"documentVersionId": "v", "indexReleaseId": "i", "contentHash": "h"}]}]}
        annotation = {"runId": "r", "category": "事实错误", "reviewer": "reviewer-1", "question": "sanitized", "expectedFacts": ["fact"], "expectedDocumentVersionIds": ["v"], "expectedAnswerMode": "COMPANY_KNOWLEDGE", "approved": True}
        exported = pilot.export_cases(raw, [annotation])
        self.assertEqual(exported["cases"][0]["question"], "sanitized")
        self.assertEqual(exported["sources"][0]["runId"], "r")
        annotation["expectedAnswerMode"] = "ANSWER"
        with self.assertRaises(ValueError):
            pilot.export_cases(raw, [annotation])
        annotation["expectedAnswerMode"] = "COMPANY_KNOWLEDGE"
        annotation["expectedFacts"] = [" "]
        with self.assertRaises(ValueError):
            pilot.export_cases(raw, [annotation])
        annotation["expectedFacts"] = ["fact"]
        annotation["approved"] = False
        with self.assertRaises(ValueError):
            pilot.export_cases(raw, [annotation])

    def test_import_does_not_write_without_explicit_confirmation(self):
        def handle(request):
            self.fail("must not request API")
        with self.assertRaises(ValueError):
            pilot.import_cases(httpx.Client(transport=httpx.MockTransport(handle), base_url="http://test"), {}, "pilot-test", False)

    def test_raw_path_must_be_ignored(self):
        with self.assertRaises(ValueError):
            pilot.private_path(Path("docs/private.json"))

    def test_wrong_feedback_ownership_is_rejected(self):
        def handle(request):
            return httpx.Response(200, json={"data": {"items": [{"id": "f", "runId": "someone-else"}], "total": 1}})
        with self.assertRaises(ValueError):
            pilot.collect(httpx.Client(transport=httpx.MockTransport(handle), base_url="http://test"), ["r"], ["f"])

    def test_import_creates_only_new_independent_dataset(self):
        calls = []
        def handle(request):
            calls.append((request.method, request.url.path))
            if request.method == "GET":
                return httpx.Response(200, json={"data": [{"name": "baseline"}]})
            if request.url.path.endswith("/datasets"):
                return httpx.Response(200, json={"data": {"id": "new-pilot"}})
            return httpx.Response(200, json={"data": {"createdCount": 1}})
        bundle = {"cases": [{"caseNo": "pilot-r", "question": "question", "expectedAnswerMode": "COMPANY_KNOWLEDGE", "expectedFacts": ["fact"], "prohibitedFacts": [], "expectedDocumentTitles": [], "expectedDocumentVersionIds": [], "tags": [], "minCitationCount": 0}], "sources": [{"runId": "r"}], "sourceSha256": "hash"}
        result = pilot.import_cases(httpx.Client(transport=httpx.MockTransport(handle), base_url="http://test"), bundle, "pilot-new", True)
        self.assertEqual(result["datasetId"], "new-pilot")
        self.assertEqual(calls[-1], ("POST", "/api/aihub/rag-evaluations/datasets/new-pilot/cases/import"))

    def test_import_refuses_existing_dataset(self):
        def handle(request):
            self.assertEqual(request.method, "GET")
            return httpx.Response(200, json={"data": [{"name": "pilot-existing"}]})
        bundle = {"cases": [{}], "sources": [{}], "sourceSha256": "hash"}
        with self.assertRaises(ValueError):
            pilot.import_cases(httpx.Client(transport=httpx.MockTransport(handle), base_url="http://test"), bundle, "pilot-existing", True)

    def test_corrupt_import_is_rejected_before_any_request(self):
        def handle(request):
            self.fail("invalid bundle must fail before API")
        client = httpx.Client(transport=httpx.MockTransport(handle), base_url="http://test")
        valid = {"caseNo": "pilot-r", "question": "question", "expectedAnswerMode": "COMPANY_KNOWLEDGE", "expectedFacts": ["fact"], "prohibitedFacts": [], "expectedDocumentTitles": [], "expectedDocumentVersionIds": [], "tags": [], "minCitationCount": 0}
        for key, value in [("question", "  "), ("expectedFacts", [" "]), ("expectedFacts", [7]), ("tags", [None]), ("minCitationCount", True), ("minCitationCount", -1)]:
            with self.subTest(key=key, value=value):
                case = {**valid, key: value}
                with self.assertRaises(ValueError):
                    pilot.import_cases(client, {"cases": [case], "sources": [{}], "sourceSha256": "h"}, "pilot-new", True)


if __name__ == "__main__":
    unittest.main()

