from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.stats import chi2_contingency
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer


TOKEN_RE = re.compile(r"[a-z][a-z'-]+")
NEGATION_RE = re.compile(r"\b(?:not|no|never|without|hardly|isn't|aren't|wasn't|weren't|doesn't|don't|didn't)\b")


def load_codebook(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def phrase_count(text: str, phrases: list[str]) -> int:
    lower = text.lower()
    return sum(lower.count(p.lower()) for p in phrases)


def best_label(text: str, mapping: dict[str, list[str]], default: str) -> tuple[str, int, str]:
    scored = []
    for label, terms in mapping.items():
        hits = [(term, phrase_count(text, [term])) for term in terms]
        score = sum(n for _, n in hits)
        matched = "; ".join(term for term, n in hits if n)
        scored.append((score, label, matched))
    scored.sort(key=lambda x: (-x[0], x[1]))
    score, label, matched = scored[0]
    return (label, score, matched) if score else (default, 0, "")


def classify_stance(text: str, mapping: dict[str, list[str]]) -> tuple[str, int, str]:
    scores = {label: phrase_count(text, terms) for label, terms in mapping.items()}
    if scores.get("Supportive", 0) and scores.get("Critical", 0):
        return "Uncertain/Mixed", scores["Supportive"] + scores["Critical"], "supportive+critical"
    maximum = max(scores.values(), default=0)
    if maximum == 0:
        return "Neutral", 0, ""
    winners = [k for k, v in scores.items() if v == maximum]
    label = "Uncertain/Mixed" if len(winners) > 1 else winners[0]
    matched = "; ".join(t for t in mapping.get(label, []) if t.lower() in text.lower())
    if label == "Supportive" and NEGATION_RE.search(text.lower()):
        label = "Uncertain/Mixed"
    return label, maximum, matched


def cramers_v(table: pd.DataFrame, chi2: float) -> float:
    n = table.to_numpy().sum()
    denom = n * max(1, min(table.shape[0] - 1, table.shape[1] - 1))
    return math.sqrt(chi2 / denom) if denom else float("nan")


def adjusted_residuals(table: pd.DataFrame) -> pd.DataFrame:
    obs = table.to_numpy(dtype=float)
    n = obs.sum()
    row = obs.sum(axis=1, keepdims=True)
    col = obs.sum(axis=0, keepdims=True)
    expected = row @ col / n
    denom = np.sqrt(expected * (1 - row / n) * (1 - col / n))
    residuals = np.divide(obs - expected, denom, out=np.zeros_like(obs), where=denom != 0)
    return pd.DataFrame(residuals, index=table.index, columns=table.columns)


def analyse_dimension(df: pd.DataFrame, variable: str, output: Path) -> dict:
    counts = pd.crosstab(df["source_type"], df[variable])
    percentages = counts.div(counts.sum(axis=1), axis=0) * 100
    chi2, p, dof, _ = chi2_contingency(counts)
    residuals = adjusted_residuals(counts)
    counts.to_csv(output / f"{variable}_counts.csv", encoding="utf-8-sig")
    percentages.to_csv(output / f"{variable}_within_community_percent.csv", encoding="utf-8-sig")
    residuals.to_csv(output / f"{variable}_adjusted_residuals.csv", encoding="utf-8-sig")
    return {"variable": variable, "chi_square": chi2, "df": int(dof), "p": p, "cramers_v": cramers_v(counts, chi2)}


def lexical_outputs(df: pd.DataFrame, output: Path) -> None:
    grouped = df.groupby("source_type")["sentence"].apply(lambda x: " ".join(x.astype(str))).to_dict()
    labels = list(grouped)
    texts = [grouped[k] for k in labels]
    tfidf = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=2, max_features=4000)
    matrix = tfidf.fit_transform(texts)
    terms = np.array(tfidf.get_feature_names_out())
    rows = []
    for i, label in enumerate(labels):
        values = matrix[i].toarray().ravel()
        for idx in values.argsort()[::-1][:50]:
            rows.append({"source_type": label, "term": terms[idx], "tfidf": values[idx]})
    pd.DataFrame(rows).to_csv(output / "community_tfidf_terms.csv", index=False, encoding="utf-8-sig")

    vectorizer = CountVectorizer(stop_words="english", ngram_range=(1, 2), min_df=5, max_features=6000)
    counts = vectorizer.fit_transform(df["sentence"].fillna(""))
    vocab = np.array(vectorizer.get_feature_names_out())
    keyword_rows = []
    for community in sorted(df["source_type"].unique()):
        mask = (df["source_type"] == community).to_numpy()
        a = np.asarray(counts[mask].sum(axis=0)).ravel() + 0.5
        b = np.asarray(counts[~mask].sum(axis=0)).ravel() + 0.5
        n1, n2 = a.sum(), b.sum()
        log_ratio = np.log2((a / n1) / (b / n2))
        for idx in log_ratio.argsort()[::-1][:50]:
            keyword_rows.append({"source_type": community, "term": vocab[idx], "log2_ratio": log_ratio[idx], "community_count": int(a[idx] - 0.5), "other_count": int(b[idx] - 0.5)})
    pd.DataFrame(keyword_rows).to_csv(output / "community_keyness_log_ratio.csv", index=False, encoding="utf-8-sig")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local reproducible hookless corpus analysis")
    parser.add_argument("sentence_csv", type=Path)
    parser.add_argument("codebook", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()

    output = args.output_directory
    output.mkdir(parents=True, exist_ok=True)
    codebook = load_codebook(args.codebook)
    df = pd.read_csv(args.sentence_csv, encoding="utf-8-sig", low_memory=False).fillna("")

    coded_rows = []
    for row in df.to_dict("records"):
        text = str(row.get("sentence", ""))
        theme, theme_score, theme_terms = best_label(text, codebook["primary_theme"], "Other/Unclassified")
        stance, stance_score, stance_terms = classify_stance(text, codebook["stance"])
        authority, authority_score, authority_terms = best_label(text, codebook["authority_invoked"], "None")
        evidence, evidence_score, evidence_terms = best_label(text, codebook["evidence_type"], "None")
        row.update({
            "primary_theme": theme,
            "stance": stance,
            "authority_invoked": authority,
            "evidence_type": evidence,
            "theme_score": theme_score,
            "stance_score": stance_score,
            "authority_score": authority_score,
            "evidence_score": evidence_score,
            "theme_matches": theme_terms,
            "stance_matches": stance_terms,
            "authority_matches": authority_terms,
            "evidence_matches": evidence_terms,
            "manual_review_flag": "YES" if theme_score == 0 or (stance_score + authority_score + evidence_score == 0) else "NO",
        })
        coded_rows.append(row)
    coded = pd.DataFrame(coded_rows)
    coded.to_csv(output / "coded_sentence_corpus.csv", index=False, encoding="utf-8-sig")

    document_profiles = (
        coded.groupby(["document_id", "source_type", "source_name", "url"])
        .agg(sentences=("sentence_id", "count"),
             theme_classified=("theme_score", lambda x: int((x > 0).sum())),
             evaluative_sentences=("stance_score", lambda x: int((x > 0).sum())),
             authority_sentences=("authority_score", lambda x: int((x > 0).sum())),
             evidence_sentences=("evidence_score", lambda x: int((x > 0).sum())))
        .reset_index()
    )
    document_profiles.to_csv(output / "document_profiles.csv", index=False, encoding="utf-8-sig")

    corpus_summary = {
        "documents": int(coded["document_id"].nunique()),
        "sentences": int(len(coded)),
        "by_community_documents": coded.groupby("source_type")["document_id"].nunique().astype(int).to_dict(),
        "by_community_sentences": coded["source_type"].value_counts().astype(int).to_dict(),
        "codebook_version": codebook.get("version", "unknown"),
        "theme_classification_rate": float((coded["theme_score"] > 0).mean()),
        "evaluative_stance_rate": float((coded["stance_score"] > 0).mean()),
        "authority_invocation_rate": float((coded["authority_score"] > 0).mean()),
        "explicit_evidence_rate": float((coded["evidence_score"] > 0).mean()),
    }
    (output / "corpus_summary.json").write_text(json.dumps(corpus_summary, indent=2), encoding="utf-8")

    tests = []
    for variable in ["primary_theme", "stance", "authority_invoked", "evidence_type"]:
        tests.append(analyse_dimension(coded, variable, output))
    pd.DataFrame(tests).to_csv(output / "inferential_tests.csv", index=False, encoding="utf-8-sig")

    lexical_outputs(coded, output)

    with pd.ExcelWriter(output / "analysis_results.xlsx", engine="openpyxl") as writer:
        pd.DataFrame([corpus_summary]).to_excel(writer, sheet_name="Corpus Summary", index=False)
        pd.DataFrame(tests).to_excel(writer, sheet_name="Inferential Tests", index=False)
        document_profiles.to_excel(writer, sheet_name="Document Profiles", index=False)
        for variable in ["primary_theme", "stance", "authority_invoked", "evidence_type"]:
            pd.crosstab(coded["source_type"], coded[variable]).to_excel(writer, sheet_name=f"{variable[:20]} counts")
            (pd.crosstab(coded["source_type"], coded[variable], normalize="index") * 100).to_excel(writer, sheet_name=f"{variable[:20]} pct")

    print(json.dumps(corpus_summary, indent=2))
    print("\nInferential tests")
    print(pd.DataFrame(tests).to_string(index=False))
    print(f"\nOutputs written to: {output}")


if __name__ == "__main__":
    main()
