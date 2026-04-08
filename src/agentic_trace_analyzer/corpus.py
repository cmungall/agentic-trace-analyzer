"""Corpus manifests and trace artifact resolution helpers."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import yaml

from agentic_trace_analyzer.ontology import ontology_index

FETCHABLE_LOCATOR_KINDS = {"local_file", "github_blob", "http"}


class CorpusError(ValueError):
    """Base error raised for invalid corpus manifests."""


class UnsupportedLocatorError(CorpusError):
    """Raised when an artifact uses a locator kind without an adapter."""


class ArtifactFetchError(CorpusError):
    """Raised when an artifact cannot be resolved to a local file."""


@dataclass(slots=True)
class ArtifactLocator:
    """Location metadata for a trace artifact."""

    kind: str
    value: str

    def is_fetchable(self) -> bool:
        """Return whether the current repo knows how to materialize this locator."""
        return self.kind in FETCHABLE_LOCATOR_KINDS

    def to_dict(self) -> dict[str, str]:
        """Convert the locator into a JSON-serializable dict."""
        return {"kind": self.kind, "value": self.value}


@dataclass(slots=True)
class TraceArtifact:
    """A single trace artifact entry in a corpus manifest."""

    artifact_id: str
    title: str
    locator: ArtifactLocator
    trace_format: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    access: str | None = None
    license: str | None = None
    review_status: str = "unreviewed"
    expected_failure_modes: list[str] = field(default_factory=list)
    expected_absent_failure_modes: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    notes: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_expectations(self) -> bool:
        """Return whether this artifact has reviewed label assertions."""
        return bool(self.expected_failure_modes or self.expected_absent_failure_modes)

    def to_dict(self) -> dict[str, Any]:
        """Convert the artifact into a JSON-serializable dict."""
        return {
            "id": self.artifact_id,
            "title": self.title,
            "locator": self.locator.to_dict(),
            "trace_format": self.trace_format,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "access": self.access,
            "license": self.license,
            "review_status": self.review_status,
            "expected_failure_modes": self.expected_failure_modes,
            "expected_absent_failure_modes": self.expected_absent_failure_modes,
            "tags": self.tags,
            "notes": self.notes,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class TraceCorpusManifest:
    """A corpus manifest defining candidate trace artifacts and annotations."""

    version: int
    name: str
    source_path: Path
    description: str | None = None
    artifacts: list[TraceArtifact] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert the manifest into a JSON-serializable dict."""
        return {
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "source_path": str(self.source_path),
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
        }


@dataclass(slots=True)
class ResolvedTraceArtifact:
    """A trace artifact with a local path ready for parsing."""

    artifact: TraceArtifact
    local_path: Path

    def to_dict(self) -> dict[str, Any]:
        """Convert the resolved artifact into a JSON-serializable dict."""
        return {
            "artifact": self.artifact.to_dict(),
            "local_path": str(self.local_path),
        }


def load_corpus_manifest(path: Path) -> TraceCorpusManifest:
    """Load and validate a trace corpus manifest from YAML."""
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    version = raw.get("version")
    name = raw.get("name")
    if not isinstance(version, int):
        raise CorpusError(f"{path}: `version` must be an integer.")
    if not isinstance(name, str) or not name.strip():
        raise CorpusError(f"{path}: `name` must be a non-empty string.")

    artifacts_raw = raw.get("artifacts")
    if not isinstance(artifacts_raw, list):
        raise CorpusError(f"{path}: `artifacts` must be a list.")

    seen_ids: set[str] = set()
    artifacts: list[TraceArtifact] = []
    valid_failure_mode_ids = set(ontology_index())

    for index, artifact_raw in enumerate(artifacts_raw, start=1):
        if not isinstance(artifact_raw, dict):
            raise CorpusError(f"{path}: artifact #{index} must be a mapping.")

        artifact_id = artifact_raw.get("id")
        title = artifact_raw.get("title")
        locator_raw = artifact_raw.get("locator")
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            raise CorpusError(f"{path}: artifact #{index} is missing a valid `id`.")
        if artifact_id in seen_ids:
            raise CorpusError(f"{path}: duplicate artifact id `{artifact_id}`.")
        seen_ids.add(artifact_id)
        if not isinstance(title, str) or not title.strip():
            raise CorpusError(f"{path}: artifact `{artifact_id}` is missing a valid `title`.")
        if not isinstance(locator_raw, dict):
            raise CorpusError(f"{path}: artifact `{artifact_id}` is missing a valid `locator`.")

        locator_kind = locator_raw.get("kind")
        locator_value = locator_raw.get("value")
        if not isinstance(locator_kind, str) or not isinstance(locator_value, str):
            raise CorpusError(
                f"{path}: artifact `{artifact_id}` locator needs string `kind` and `value`."
            )

        expected_present = _normalize_label_list(
            path=path,
            artifact_id=artifact_id,
            field_name="expected_failure_modes",
            value=artifact_raw.get("expected_failure_modes", []),
            valid_failure_mode_ids=valid_failure_mode_ids,
        )
        expected_absent = _normalize_label_list(
            path=path,
            artifact_id=artifact_id,
            field_name="expected_absent_failure_modes",
            value=artifact_raw.get("expected_absent_failure_modes", []),
            valid_failure_mode_ids=valid_failure_mode_ids,
        )

        artifacts.append(
            TraceArtifact(
                artifact_id=artifact_id,
                title=title,
                locator=ArtifactLocator(kind=locator_kind, value=locator_value),
                trace_format=_optional_string(artifact_raw.get("trace_format")),
                source_name=_optional_string(artifact_raw.get("source_name")),
                source_url=_optional_string(artifact_raw.get("source_url")),
                access=_optional_string(artifact_raw.get("access")),
                license=_optional_string(artifact_raw.get("license")),
                review_status=_optional_string(artifact_raw.get("review_status")) or "unreviewed",
                expected_failure_modes=expected_present,
                expected_absent_failure_modes=expected_absent,
                tags=_normalize_string_list(
                    path=path,
                    artifact_id=artifact_id,
                    field_name="tags",
                    value=artifact_raw.get("tags", []),
                ),
                notes=_optional_string(artifact_raw.get("notes")),
                metadata=artifact_raw.get("metadata", {})
                if isinstance(artifact_raw.get("metadata"), dict)
                else {},
            )
        )

    return TraceCorpusManifest(
        version=version,
        name=name,
        description=_optional_string(raw.get("description")),
        source_path=path.resolve(),
        artifacts=artifacts,
    )


def summarize_manifest(manifest: TraceCorpusManifest) -> dict[str, Any]:
    """Return a compact summary of a corpus manifest."""
    locator_counts = Counter(artifact.locator.kind for artifact in manifest.artifacts)
    review_counts = Counter(artifact.review_status for artifact in manifest.artifacts)
    return {
        "artifact_count": len(manifest.artifacts),
        "fetchable_artifact_count": sum(
            1 for artifact in manifest.artifacts if artifact.locator.is_fetchable()
        ),
        "reviewed_artifact_count": sum(
            1 for artifact in manifest.artifacts if artifact.has_expectations()
        ),
        "locator_counts": dict(locator_counts.most_common()),
        "review_status_counts": dict(review_counts.most_common()),
    }


def resolve_trace_artifact(
    artifact: TraceArtifact,
    manifest_path: Path,
    cache_dir: Path | None = None,
) -> ResolvedTraceArtifact:
    """Resolve an artifact to a local file path, fetching remote content if needed."""
    if artifact.locator.kind == "local_file":
        local_path = Path(artifact.locator.value)
        if not local_path.is_absolute():
            local_path = manifest_path.parent / local_path
        local_path = local_path.resolve()
        if not local_path.exists():
            raise ArtifactFetchError(
                f"Artifact `{artifact.artifact_id}` points to missing file `{local_path}`."
            )
        return ResolvedTraceArtifact(artifact=artifact, local_path=local_path)

    if artifact.locator.kind == "github_blob":
        if cache_dir is None:
            raise ArtifactFetchError(
                f"Artifact `{artifact.artifact_id}` needs `cache_dir` for remote fetches."
            )
        raw_url = github_blob_to_raw_url(artifact.locator.value)
        return ResolvedTraceArtifact(
            artifact=artifact,
            local_path=_download_to_cache(raw_url, cache_dir),
        )

    if artifact.locator.kind == "http":
        if cache_dir is None:
            raise ArtifactFetchError(
                f"Artifact `{artifact.artifact_id}` needs `cache_dir` for remote fetches."
            )
        return ResolvedTraceArtifact(
            artifact=artifact,
            local_path=_download_to_cache(artifact.locator.value, cache_dir),
        )

    raise UnsupportedLocatorError(
        f"Artifact `{artifact.artifact_id}` uses unsupported locator kind "
        f"`{artifact.locator.kind}`."
    )


def github_blob_to_raw_url(url: str) -> str:
    """Convert a GitHub blob URL into a raw.githubusercontent URL."""
    parsed = urlparse(url)
    if parsed.netloc == "raw.githubusercontent.com":
        return url
    if parsed.netloc not in {"github.com", "www.github.com"}:
        raise ArtifactFetchError(f"Unsupported GitHub blob URL host: `{parsed.netloc}`.")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 5 or parts[2] != "blob":
        raise ArtifactFetchError(f"Unsupported GitHub blob URL shape: `{url}`.")

    owner, repo, _, ref, *path_parts = parts
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{'/'.join(path_parts)}"


def _download_to_cache(url: str, cache_dir: Path) -> Path:
    """Download a remote artifact into the cache directory."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix or ".trace"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
    local_path = cache_dir / f"{digest}{suffix}"
    if local_path.exists():
        return local_path

    request = Request(url, headers={"User-Agent": "agentic-trace-analyzer/0.1"})
    try:
        with urlopen(request) as response:
            content = response.read()
    except Exception as exc:  # pragma: no cover - network failures are environment-specific
        raise ArtifactFetchError(f"Failed to download `{url}`: {exc}") from exc

    local_path.write_bytes(content)
    return local_path


def _normalize_label_list(
    path: Path,
    artifact_id: str,
    field_name: str,
    value: Any,
    valid_failure_mode_ids: set[str],
) -> list[str]:
    labels = _normalize_string_list(
        path=path,
        artifact_id=artifact_id,
        field_name=field_name,
        value=value,
    )
    unknown = [label for label in labels if label not in valid_failure_mode_ids]
    if unknown:
        raise CorpusError(
            f"{path}: artifact `{artifact_id}` field `{field_name}` has unknown "
            f"failure mode ids: {', '.join(sorted(unknown))}."
        )
    return labels


def _normalize_string_list(
    path: Path,
    artifact_id: str,
    field_name: str,
    value: Any,
) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CorpusError(
            f"{path}: artifact `{artifact_id}` field `{field_name}` must be a list of strings."
        )
    return value


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise CorpusError(f"Expected a string or null, got `{type(value).__name__}`.")
