from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def prepare(screening_path: Path, review_path: Path) -> None:
    rows = [r for r in read_rows(screening_path) if r.get("screening_decision") == "Include"]
    fields = [
        "keep", "manual_reason", "source_type", "source_name", "title", "url",
        "word_count", "publication_date", "discovery_query", "local_text_path",
    ]
    with review_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "keep": "YES",
                "manual_reason": "",
                "source_type": row.get("source_type", ""),
                "source_name": row.get("source_name", ""),
                "title": row.get("title", ""),
                "url": row.get("url", ""),
                "word_count": row.get("word_count", ""),
                "publication_date": row.get("publication_date", ""),
                "discovery_query": row.get("discovery_query", ""),
                "local_text_path": row.get("local_text_path", ""),
            })
    print(f"Created {review_path} with {len(rows)} included documents.")
    print("Change keep from YES to NO only for documents that should be removed.")


def apply(review_path: Path, output_dir: Path) -> None:
    rows = read_rows(review_path)
    kept = [r for r in rows if r.get("keep", "").strip().upper() not in {"NO", "N", "0", "FALSE"}]
    removed = [r for r in rows if r not in kept]
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_fields = ["url", "source_type", "source_name", "publication_date", "notes", "discovery_query"]
    with (output_dir / "final_document_manifest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=manifest_fields)
        writer.writeheader()
        for row in kept:
            writer.writerow({
                "url": row.get("url", ""),
                "source_type": row.get("source_type", ""),
                "source_name": row.get("source_name", ""),
                "publication_date": row.get("publication_date", ""),
                "notes": f"manual_review=keep; words={row.get('word_count', '')}",
                "discovery_query": row.get("discovery_query", ""),
            })

    sentence_fields = [
        "sentence_id", "document_id", "source_type", "source_name", "url", "sentence",
        "previous_sentence", "next_sentence",
    ]
    sentence_count = 0
    missing_files: list[str] = []
    with (output_dir / "final_sentence_corpus.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=sentence_fields)
        writer.writeheader()
        for document_id, row in enumerate(kept, start=1):
            path = Path(row.get("local_text_path", ""))
            if not path.exists():
                missing_files.append(str(path))
                continue
            text = re.sub(r"\s+", " ", path.read_text(encoding="utf-8")).strip()
            sentences = [s.strip() for s in SENTENCE_RE.split(text) if len(s.split()) >= 4]
            for index, sentence in enumerate(sentences):
                sentence_count += 1
                writer.writerow({
                    "sentence_id": sentence_count,
                    "document_id": document_id,
                    "source_type": row.get("source_type", ""),
                    "source_name": row.get("source_name", ""),
                    "url": row.get("url", ""),
                    "sentence": sentence,
                    "previous_sentence": sentences[index - 1] if index else "",
                    "next_sentence": sentences[index + 1] if index + 1 < len(sentences) else "",
                })

    with (output_dir / "manual_exclusions.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = ["source_type", "source_name", "title", "url", "manual_reason"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in removed:
            writer.writerow({field: row.get(field, "") for field in fields})

    counts = Counter(row.get("source_type", "") for row in kept)
    summary = {
        "documents_reviewed": len(rows),
        "documents_kept": len(kept),
        "documents_removed": len(removed),
        "sentences": sentence_count,
        "by_community": dict(counts),
        "missing_text_files": missing_files,
    }
    (output_dir / "final_run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Review and rebuild a CDAT corpus without repeating web collection")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare_parser = sub.add_parser("prepare", help="Create an editable review sheet from included documents")
    prepare_parser.add_argument("screening_csv", type=Path)
    prepare_parser.add_argument("review_csv", type=Path)

    apply_parser = sub.add_parser("apply", help="Apply review decisions and rebuild clean outputs")
    apply_parser.add_argument("review_csv", type=Path)
    apply_parser.add_argument("output_dir", type=Path)

    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.screening_csv, args.review_csv)
    else:
        apply(args.review_csv, args.output_dir)


if __name__ == "__main__":
    main()
