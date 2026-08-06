from __future__ import annotations

import argparse
import csv
import json
import os
import time
from pathlib import Path

from openai import OpenAI

THEMES = [
    "Risk & Safety", "Performance", "Compatibility", "Standards & Regulation",
    "Engineering & Design", "User Experience", "Responsibility & Liability",
    "Commercialisation",
]
STANCES = ["Supportive", "Critical", "Neutral", "Uncertain/Mixed"]
AUTHORITIES = [
    "Manufacturer", "Standards/Regulatory Body", "Technical Expert", "Media",
    "Rider Community", "None",
]
EVIDENCE = [
    "Empirical Test Data", "Incident/Case", "Personal Experience",
    "Formal Rule/Guidance", "Expert Opinion", "Commercial Claim", "None",
]

SYSTEM_PROMPT = """You are a research annotation assistant for a corpus-assisted discourse study of hookless bicycle rim technology.
Code each focal sentence independently while using its previous and next sentence only to resolve context.
Assign exactly one category for each dimension.

PRIMARY THEME
- Risk & Safety: hazards, failures, crashes, blow-offs, injury, safety judgements.
- Performance: speed, rolling resistance, aerodynamics, weight, efficiency, racing performance.
- Compatibility: tyre/rim fit, approved combinations, widths, pressures, installation compatibility.
- Standards & Regulation: formal standards, rules, limits, certification, governing-body action.
- Engineering & Design: construction, tolerances, materials, manufacturing, rim/tyre design.
- User Experience: riding, ownership, installation or maintenance experience and practical usability.
- Responsibility & Liability: blame, duty, accountability, warnings, legal or ethical responsibility.
- Commercialisation: pricing, marketing, sales, cost-saving, product positioning or adoption strategy.

STANCE
- Supportive: endorses or positively evaluates hookless technology.
- Critical: rejects, condemns or negatively evaluates it.
- Neutral: descriptive or informational without clear evaluation.
- Uncertain/Mixed: explicitly cautious, ambivalent, disputed or unresolved.

AUTHORITY INVOKED
Code the principal source treated as knowledgeable: Manufacturer; Standards/Regulatory Body; Technical Expert; Media; Rider Community; None.
Do not automatically code the document's own community as authority. Code only authority invoked in the focal claim.

EVIDENCE TYPE
Code the principal support used: Empirical Test Data; Incident/Case; Personal Experience; Formal Rule/Guidance; Expert Opinion; Commercial Claim; None.
Commercial Claim means an unsupported promotional or product claim. If no explicit justification is present, use None.

CONFIDENCE
Integer 0-100 reflecting confidence in the complete four-part annotation.
Return only data matching the supplied JSON schema. Preserve every sentence_id exactly."""


def schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "annotations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "sentence_id": {"type": "integer"},
                        "primary_theme": {"type": "string", "enum": THEMES},
                        "stance": {"type": "string", "enum": STANCES},
                        "authority_invoked": {"type": "string", "enum": AUTHORITIES},
                        "evidence_type": {"type": "string", "enum": EVIDENCE},
                        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                    },
                    "required": ["sentence_id", "primary_theme", "stance", "authority_invoked", "evidence_type", "confidence"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["annotations"],
        "additionalProperties": False,
    }


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def completed_ids(path: Path) -> set[int]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {int(row["sentence_id"]) for row in csv.DictReader(handle)}


def write_batch(path: Path, source_by_id: dict[int, dict[str, str]], annotations: list[dict]) -> None:
    fields = [
        "sentence_id", "document_id", "source_type", "source_name", "url", "sentence",
        "previous_sentence", "next_sentence", "primary_theme", "stance",
        "authority_invoked", "evidence_type", "confidence",
    ]
    new_file = not path.exists() or path.stat().st_size == 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if new_file:
            writer.writeheader()
        for annotation in annotations:
            sid = int(annotation["sentence_id"])
            source = source_by_id[sid]
            writer.writerow({**{field: source.get(field, "") for field in fields[:8]}, **annotation})


def payload(rows: list[dict[str, str]]) -> str:
    records = []
    for row in rows:
        records.append({
            "sentence_id": int(row["sentence_id"]),
            "community": row.get("source_type", ""),
            "previous_sentence": row.get("previous_sentence", ""),
            "focal_sentence": row.get("sentence", ""),
            "next_sentence": row.get("next_sentence", ""),
        })
    return json.dumps(records, ensure_ascii=False)


def annotate_batch(client: OpenAI, model: str, rows: list[dict[str, str]]) -> list[dict]:
    response = client.responses.create(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=payload(rows),
        text={
            "format": {
                "type": "json_schema",
                "name": "hookless_annotations",
                "strict": True,
                "schema": schema(),
            }
        },
    )
    data = json.loads(response.output_text)
    annotations = data["annotations"]
    expected = {int(row["sentence_id"]) for row in rows}
    received = {int(item["sentence_id"]) for item in annotations}
    if expected != received:
        raise ValueError(f"ID mismatch. Missing={sorted(expected-received)} extra={sorted(received-expected)}")
    return annotations


def main() -> None:
    parser = argparse.ArgumentParser(description="Annotate a CDAT sentence corpus with a fixed deductive codebook")
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--model", default="gpt-5-mini")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--limit", type=int, default=0, help="Maximum new sentences to annotate; 0 means all")
    parser.add_argument("--retries", type=int, default=4)
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set. Export it in Terminal before running.")
    if args.batch_size < 1 or args.batch_size > 100:
        raise SystemExit("--batch-size must be between 1 and 100")

    rows = read_rows(args.input_csv)
    done = completed_ids(args.output_csv)
    pending = [row for row in rows if int(row["sentence_id"]) not in done]
    if args.limit:
        pending = pending[:args.limit]
    source_by_id = {int(row["sentence_id"]): row for row in rows}
    client = OpenAI()

    print(f"Input sentences: {len(rows)}", flush=True)
    print(f"Already annotated: {len(done)}", flush=True)
    print(f"New sentences this run: {len(pending)}", flush=True)
    print(f"Model: {args.model}; batch size: {args.batch_size}", flush=True)

    for start in range(0, len(pending), args.batch_size):
        batch = pending[start:start + args.batch_size]
        batch_no = start // args.batch_size + 1
        total_batches = (len(pending) + args.batch_size - 1) // args.batch_size
        print(f"Batch {batch_no}/{total_batches}: sentence {batch[0]['sentence_id']}–{batch[-1]['sentence_id']}", flush=True)
        for attempt in range(1, args.retries + 1):
            try:
                annotations = annotate_batch(client, args.model, batch)
                write_batch(args.output_csv, source_by_id, annotations)
                break
            except Exception as exc:
                if attempt == args.retries:
                    raise
                wait = min(60, 2 ** attempt)
                print(f"  attempt {attempt} failed: {type(exc).__name__}: {exc}; retrying in {wait}s", flush=True)
                time.sleep(wait)

    final_done = completed_ids(args.output_csv)
    print(f"Completed annotations in output: {len(final_done)}", flush=True)
    print(f"Saved: {args.output_csv}", flush=True)


if __name__ == "__main__":
    main()
