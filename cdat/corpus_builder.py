from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import requests
import trafilatura
import yaml
from ddgs import DDGS
from langdetect import detect, LangDetectException


SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")
TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass
class Record:
    url: str
    canonical_url: str
    source_type: str
    source_name: str
    discovery_query: str
    search_rank: int
    title: str = ""
    publication_date: str = ""
    word_count: int = 0
    language: str = ""
    text_sha256: str = ""
    screening_decision: str = "Pending"
    exclusion_reason: str = ""
    local_text_path: str = ""


def canonicalise_url(url: str) -> str:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().removeprefix("www.")
    path = re.sub(r"/+", "/", parsed.path).rstrip("/")
    return urlunparse((parsed.scheme.lower() or "https", host, path, "", "", ""))


def tokens(text: str) -> set[str]:
    return set(TOKEN_RE.findall(text.lower()))


def jaccard(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def discover(config: dict) -> list[Record]:
    rows: list[Record] = []
    seen: set[str] = set()
    for community, spec in config["communities"].items():
        for domain in spec["domains"]:
            for query in config["query_families"]:
                full_query = f"site:{domain} {query}"
                try:
                    results = DDGS().text(full_query, max_results=20)
                except Exception as exc:
                    print(f"SEARCH ERROR {full_query}: {exc}")
                    continue
                for rank, result in enumerate(results, start=1):
                    url = result.get("href") or result.get("url") or ""
                    if not url:
                        continue
                    canonical = canonicalise_url(url)
                    if canonical in seen:
                        continue
                    seen.add(canonical)
                    rows.append(Record(
                        url=url,
                        canonical_url=canonical,
                        source_type=community,
                        source_name=domain,
                        discovery_query=full_query,
                        search_rank=rank,
                        title=result.get("title", ""),
                    ))
                time.sleep(0.15)
    return rows


def extract_record(record: Record, config: dict, text_dir: Path) -> Record:
    screening = config["screening"]
    if any(fragment in record.canonical_url.lower() for fragment in screening["excluded_url_fragments"]):
        record.screening_decision = "Exclude"
        record.exclusion_reason = "Excluded URL pattern"
        return record
    try:
        response = requests.get(record.url, timeout=20, headers={"User-Agent": "CDAT-Professional/0.2 corpus research"})
        response.raise_for_status()
    except Exception as exc:
        record.screening_decision = "Exclude"
        record.exclusion_reason = f"Download failure: {type(exc).__name__}"
        return record
    text = trafilatura.extract(response.text, include_comments=True, include_tables=False, favor_recall=True) or ""
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        record.screening_decision = "Exclude"
        record.exclusion_reason = "No extractable text"
        return record
    lower = text.lower()
    if not all(term.lower() in lower for term in screening["required_terms"]):
        record.screening_decision = "Exclude"
        record.exclusion_reason = "Missing required term"
        return record
    if not any(term.lower() in lower for term in screening["contextual_terms"]):
        record.screening_decision = "Exclude"
        record.exclusion_reason = "Missing cycling context"
        return record
    record.word_count = len(text.split())
    if record.word_count < config["project"]["minimum_words"]:
        record.screening_decision = "Exclude"
        record.exclusion_reason = "Below minimum word count"
        return record
    try:
        record.language = detect(text[:5000])
    except LangDetectException:
        record.language = "unknown"
    if record.language != config["project"]["language"]:
        record.screening_decision = "Exclude"
        record.exclusion_reason = f"Language: {record.language}"
        return record
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    record.text_sha256 = digest
    path = text_dir / f"{digest[:16]}.txt"
    path.write_text(text, encoding="utf-8")
    record.local_text_path = str(path)
    record.screening_decision = "Include"
    return record


def deduplicate(records: list[Record], threshold: float) -> None:
    included = [r for r in records if r.screening_decision == "Include"]
    exact: dict[str, Record] = {}
    retained: list[Record] = []
    for record in included:
        if record.text_sha256 in exact:
            record.screening_decision = "Exclude"
            record.exclusion_reason = "Exact duplicate text"
            continue
        exact[record.text_sha256] = record
        text = Path(record.local_text_path).read_text(encoding="utf-8")
        duplicate = False
        for prior in retained:
            prior_text = Path(prior.local_text_path).read_text(encoding="utf-8")
            if jaccard(text, prior_text) >= threshold:
                record.screening_decision = "Exclude"
                record.exclusion_reason = f"Near duplicate of {prior.canonical_url}"
                duplicate = True
                break
        if not duplicate:
            retained.append(record)


def apply_quotas(records: list[Record], config: dict) -> None:
    domain_cap = config["project"]["maximum_documents_per_domain"]
    for community, spec in config["communities"].items():
        quota = spec["quota"]
        candidates = sorted(
            [r for r in records if r.source_type == community and r.screening_decision == "Include"],
            key=lambda r: (r.search_rank, -r.word_count, r.canonical_url),
        )
        selected = 0
        domain_counts: dict[str, int] = {}
        for record in candidates:
            domain = urlparse(record.canonical_url).netloc
            if selected >= quota or domain_counts.get(domain, 0) >= domain_cap:
                record.screening_decision = "Exclude"
                record.exclusion_reason = "Quota/domain cap"
                continue
            selected += 1
            domain_counts[domain] = domain_counts.get(domain, 0) + 1


def write_outputs(records: list[Record], config: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    fields = list(asdict(records[0]).keys()) if records else list(Record.__annotations__)
    with (output / "document_screening.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(asdict(r) for r in records)
    included = [r for r in records if r.screening_decision == "Include"]
    with (output / "cdat_source_manifest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields2 = ["url", "source_type", "source_name", "publication_date", "notes", "discovery_query"]
        writer = csv.DictWriter(handle, fieldnames=fields2); writer.writeheader()
        for r in included:
            writer.writerow({"url": r.url, "source_type": r.source_type, "source_name": r.source_name,
                             "publication_date": r.publication_date, "notes": f"rank={r.search_rank}; words={r.word_count}",
                             "discovery_query": r.discovery_query})
    with (output / "sentence_corpus.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields3 = ["sentence_id", "document_id", "source_type", "source_name", "url", "sentence", "previous_sentence", "next_sentence"]
        writer = csv.DictWriter(handle, fieldnames=fields3); writer.writeheader()
        sid = 0
        for did, r in enumerate(included, start=1):
            text = Path(r.local_text_path).read_text(encoding="utf-8")
            sentences = [s.strip() for s in SENTENCE_RE.split(re.sub(r"\s+", " ", text)) if len(s.split()) >= 4]
            for index, sentence in enumerate(sentences):
                sid += 1
                writer.writerow({"sentence_id": sid, "document_id": did, "source_type": r.source_type,
                                 "source_name": r.source_name, "url": r.url, "sentence": sentence,
                                 "previous_sentence": sentences[index-1] if index else "",
                                 "next_sentence": sentences[index+1] if index + 1 < len(sentences) else ""})
    summary = {"discovered": len(records), "included": len(included), "excluded": len(records) - len(included),
               "by_community": {name: sum(r.screening_decision == "Include" and r.source_type == name for r in records)
                                for name in config["communities"]}}
    (output / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a reproducible domain-based corpus for CDAT Professional")
    parser.add_argument("config", type=Path)
    parser.add_argument("--discover-only", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    output = Path(config["project"]["output_directory"])
    text_dir = output / "documents"
    text_dir.mkdir(parents=True, exist_ok=True)
    records = discover(config)
    if args.discover_only:
        write_outputs(records, config, output)
        return
    for number, record in enumerate(records, start=1):
        print(f"[{number}/{len(records)}] {record.url}")
        extract_record(record, config, text_dir)
    deduplicate(records, config["project"]["near_duplicate_threshold"])
    apply_quotas(records, config)
    write_outputs(records, config, output)


if __name__ == "__main__":
    main()
