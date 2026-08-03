from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from cdat.database import Database


VALID_DECISIONS = {"Pending", "Include", "Exclude"}
VALID_SOURCE_TYPES = {
    "Manufacturer",
    "Media",
    "Forum",
    "Standards",
    "Technical / Engineering",
    "Video Transcript",
    "Other",
}


@dataclass(slots=True)
class SourceRecord:
    id: int
    project_id: int
    url: str
    source_type: str
    source_name: str
    publication_date: str
    notes: str
    discovery_query: str
    screening_decision: str
    exclusion_reason: str


class SourceManager:
    def __init__(self, database: Database):
        self.database = database

    def add_source(
        self,
        project_id: int,
        url: str,
        source_type: str = "Other",
        source_name: str = "",
        publication_date: str = "",
        notes: str = "",
        discovery_query: str = "manual",
    ) -> bool:
        clean_url = url.strip()
        if not clean_url.startswith(("http://", "https://")):
            raise ValueError(f"Invalid URL: {clean_url}")
        clean_type = source_type.strip() or "Other"
        clean_name = source_name.strip() or urlparse(clean_url).netloc.removeprefix("www.")
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO sources (
                    project_id, url, source_type, source_name, publication_date,
                    notes, discovery_query
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    clean_url.rstrip("/"),
                    clean_type,
                    clean_name,
                    publication_date.strip(),
                    notes.strip(),
                    discovery_query.strip(),
                ),
            )
            return cursor.rowcount > 0

    def add_urls(self, project_id: int, urls: list[str], source_type: str = "Other") -> tuple[int, int]:
        added = 0
        skipped = 0
        for url in urls:
            if not url.strip():
                continue
            try:
                added += int(self.add_source(project_id, url, source_type=source_type))
            except ValueError:
                skipped += 1
        return added, skipped

    def import_csv(self, project_id: int, path: Path) -> tuple[int, int]:
        aliases = {
            "url": "url",
            "source type": "source_type",
            "source_type": "source_type",
            "source name": "source_name",
            "source_name": "source_name",
            "publication date": "publication_date",
            "publication_date": "publication_date",
            "notes": "notes",
            "discovery query": "discovery_query",
            "discovery_query": "discovery_query",
        }
        added = 0
        skipped = 0
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ValueError("The CSV has no header row.")
            mapped = {name: aliases.get(name.strip().lower()) for name in reader.fieldnames}
            if "url" not in mapped.values():
                raise ValueError("The CSV must contain a URL column.")
            for row in reader:
                normalised: dict[str, str] = {}
                for original, target in mapped.items():
                    if target:
                        normalised[target] = (row.get(original) or "").strip()
                try:
                    if self.add_source(
                        project_id=project_id,
                        url=normalised.get("url", ""),
                        source_type=normalised.get("source_type", "Other"),
                        source_name=normalised.get("source_name", ""),
                        publication_date=normalised.get("publication_date", ""),
                        notes=normalised.get("notes", ""),
                        discovery_query=normalised.get("discovery_query", "manual CSV"),
                    ):
                        added += 1
                except ValueError:
                    skipped += 1
        return added, skipped

    def list_sources(self, project_id: int, decision: str | None = None) -> list[SourceRecord]:
        query = "SELECT * FROM sources WHERE project_id = ?"
        params: list[object] = [project_id]
        if decision:
            query += " AND screening_decision = ?"
            params.append(decision)
        query += " ORDER BY created_at DESC, id DESC"
        with self.database.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [SourceRecord(**dict(row)) for row in rows]

    def set_decision(self, source_ids: list[int], decision: str, reason: str = "") -> None:
        if decision not in VALID_DECISIONS:
            raise ValueError(f"Invalid screening decision: {decision}")
        if not source_ids:
            return
        placeholders = ",".join("?" for _ in source_ids)
        with self.database.connect() as connection:
            connection.execute(
                f"""
                UPDATE sources
                SET screening_decision = ?, exclusion_reason = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id IN ({placeholders})
                """,
                [decision, reason.strip(), *source_ids],
            )

    def delete_sources(self, source_ids: list[int]) -> None:
        if not source_ids:
            return
        placeholders = ",".join("?" for _ in source_ids)
        with self.database.connect() as connection:
            connection.execute(f"DELETE FROM sources WHERE id IN ({placeholders})", source_ids)

    def counts(self, project_id: int) -> dict[str, int]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT screening_decision, COUNT(*) AS n
                FROM sources WHERE project_id = ?
                GROUP BY screening_decision
                """,
                (project_id,),
            ).fetchall()
        result = {"Pending": 0, "Include": 0, "Exclude": 0}
        for row in rows:
            result[row["screening_decision"]] = row["n"]
        result["Total"] = sum(result.values())
        return result

    def export_manifest(self, project_id: int, path: Path, included_only: bool = False) -> None:
        sources = self.list_sources(project_id, "Include" if included_only else None)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "url", "source_type", "source_name", "publication_date", "notes",
                "discovery_query", "screening_decision", "exclusion_reason",
            ])
            for source in sources:
                writer.writerow([
                    source.url,
                    source.source_type,
                    source.source_name,
                    source.publication_date,
                    source.notes,
                    source.discovery_query,
                    source.screening_decision,
                    source.exclusion_reason,
                ])
