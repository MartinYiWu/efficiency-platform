"""R08 固定回放清单的规模、全集与门禁正反例治理。"""

from __future__ import annotations

import json
from pathlib import Path

MANIFEST = Path(__file__).parents[3] / "fixtures/research_v2/corpus_manifest.json"


def test_corpus_manifest_has_exactly_100_documents_and_30_events() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    document_ids = []
    event_ids = []
    for event in payload["events"]:
        event_ids.append(event["event_id"])
        document_ids.extend(
            f"{payload['document_prefix']}{index:03d}"
            for index in range(event["document_start"], event["document_end"] + 1)
        )

    assert payload["document_count"] == len(document_ids) == 100
    assert payload["event_count"] == len(event_ids) == 30
    assert len(set(document_ids)) == 100
    assert len(set(event_ids)) == 30
    assert document_ids == [f"fixture-doc-{index:03d}" for index in range(1, 101)]


def test_each_hard_gate_has_frozen_positive_and_negative_case() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    coverage = {
        (item["gate"], item["expected"]) for item in payload["quality_cases"]
    }

    assert coverage == {
        (gate, expected)
        for gate in ("H1", "H2", "H3", "H4", "H5", "H6")
        for expected in ("pass", "fail")
    }
