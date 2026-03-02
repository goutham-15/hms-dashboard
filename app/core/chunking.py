from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any, Optional

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except Exception:  # pragma: no cover
    from langchain.text_splitter import RecursiveCharacterTextSplitter  # type: ignore


class TaggedRecursiveTextChunker:
    """
    Page-aware chunker that tags chunks with a report type based on page markers.

    Example combined PDF:
    - Page 1 contains "Thyrocare" marker => chunks for pages 1..9 tagged "thyrocare"
    - Page 10 contains "SecondMedic" marker => chunks for pages 10..end tagged "second_medic"
    """

    def __init__(
        self,
        *,
        chunk_size: int = 1500,
        chunk_overlap: int = 150,
        separators: Optional[list[str]] = None,
        thyrocare_markers: Optional[list[str]] = None,
        second_medic_markers: Optional[list[str]] = None,
        unknown_tag: str = "unknown",
    ) -> None:
        self.unknown_tag = unknown_tag
        self.thyrocare_markers = [m.lower() for m in (thyrocare_markers or ["thyrocare"])]
        self.second_medic_markers = [
            m.lower() for m in (second_medic_markers or ["secondmedic", "second medic"])
        ]

        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=separators or ["\n\n", "\n", " ", ""],
        )

    def detect_report_type(self, text: str) -> Optional[str]:
        """
        Detect the report type marker present on a page.

        Returns: "thyrocare" | "second_medic" | None
        """
        hay = (text or "").lower()
        if not hay.strip():
            return None

        positions: list[tuple[int, str]] = []
        for marker in self.thyrocare_markers:
            idx = hay.find(marker)
            if idx >= 0:
                positions.append((idx, "thyrocare"))
        for marker in self.second_medic_markers:
            idx = hay.find(marker)
            if idx >= 0:
                positions.append((idx, "second_medic"))

        if not positions:
            return None
        positions.sort(key=lambda x: x[0])
        return positions[0][1]

    def iter_tagged_chunks(
        self,
        pages: Iterable[tuple[int, str]],
        *,
        initial_tag: Optional[str] = None,
        extra_metadata: Optional[dict[str, Any]] = None,
    ) -> Iterator[tuple[str, dict[str, Any]]]:
        """
        Yield (chunk_text, metadata) with report_type carried forward until a new marker appears.

        Production behavior: treat each page as a single chunk (no intra-page splitting).
        """
        current_tag = (initial_tag or "").strip().lower() or None
        for page_number, page_text in pages:
            detected = self.detect_report_type(page_text)
            if detected:
                current_tag = detected

            tag = current_tag or self.unknown_tag
            cleaned = (page_text or "").strip()
            if not cleaned:
                continue

            yield cleaned, {
                "page": page_number,
                "chunk_index": 0,
                "report_type": tag,
                **(extra_metadata or {}),
            }
