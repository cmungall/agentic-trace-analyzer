import json
from pathlib import Path

import pytest

from agentic_trace_analyzer.corpus import (
    CorpusError,
    github_blob_to_raw_url,
    load_corpus_manifest,
    resolve_trace_artifact,
    summarize_manifest,
)
from agentic_trace_analyzer.evaluation import build_review_packet, evaluate_manifest

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_load_corpus_manifest_and_summarize() -> None:
    manifest = load_corpus_manifest(FIXTURES / "corpus_manifest.yaml")

    assert manifest.name == "Fixture Evaluation Corpus"
    assert len(manifest.artifacts) == 3
    summary = summarize_manifest(manifest)
    assert summary["artifact_count"] == 3
    assert summary["fetchable_artifact_count"] == 3
    assert summary["reviewed_artifact_count"] == 3
    assert summary["locator_counts"]["local_file"] == 3


def test_resolve_trace_artifact_for_local_file() -> None:
    manifest = load_corpus_manifest(FIXTURES / "corpus_manifest.yaml")
    resolved = resolve_trace_artifact(manifest.artifacts[0], manifest.source_path)

    assert resolved.local_path == FIXTURES / "codex_session.jsonl"


def test_github_blob_url_is_converted_to_raw() -> None:
    url = (
        "https://github.com/jzila/canopy/blob/675af361c4d11dca599b7bfc96ab6f54a3dd0016/"
        ".codex/sessions/2026/02/01/rollout-2026-02-01T12-19-47-019c1a6e-b191-7f32-"
        "b8d5-8d213f5420d7.jsonl"
    )

    assert github_blob_to_raw_url(url) == (
        "https://raw.githubusercontent.com/jzila/canopy/675af361c4d11dca599b7bfc96ab6f54a3dd0016/"
        ".codex/sessions/2026/02/01/rollout-2026-02-01T12-19-47-019c1a6e-b191-7f32-"
        "b8d5-8d213f5420d7.jsonl"
    )


def test_manifest_rejects_unknown_failure_mode(tmp_path: Path) -> None:
    manifest_path = tmp_path / "bad.yaml"
    manifest_path.write_text(
        """
version: 1
name: Bad manifest
artifacts:
  - id: bad
    title: Bad
    locator:
      kind: local_file
      value: trace.jsonl
    expected_failure_modes:
      - definitely_not_a_real_mode
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(CorpusError):
        load_corpus_manifest(manifest_path)


def test_evaluate_manifest_matches_fixture_expectations(tmp_path: Path) -> None:
    report = evaluate_manifest(FIXTURES / "corpus_manifest.yaml", cache_dir=tmp_path)
    summary = report.summary()

    assert summary["artifact_count"] == 3
    assert summary["evaluated_count"] == 3
    assert summary["reviewed_count"] == 3
    assert summary["status_counts"]["review_match"] == 3
    assert summary["failure_mode_counts"]["tool_misuse"] == 2
    assert summary["missing_expected_counts"] == {}
    assert summary["violated_absent_counts"] == {}


def test_build_review_packet_contains_rule_findings_and_event_digest(tmp_path: Path) -> None:
    report = evaluate_manifest(FIXTURES / "corpus_manifest.yaml", cache_dir=tmp_path, limit=1)
    item = report.artifacts[0]
    packet = build_review_packet(item, event_limit=5)

    assert packet["artifact"]["id"] == "fixture_codex"
    assert packet["session_summary"]["source"] == "codex"
    assert packet["rule_based_findings"]
    assert packet["event_digest"]["event_limit"] == 5
    assert len(packet["allowed_failure_modes"]) >= 20

    json.dumps(packet)
