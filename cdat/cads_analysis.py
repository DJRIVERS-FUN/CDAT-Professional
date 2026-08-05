from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
from scipy.stats import chi2_contingency
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

TOKEN_RE = re.compile(r"[a-z][a-z'-]+")
STOPWORDS = set(ENGLISH_STOP_WORDS) | {
    'hookless','rim','rims','wheel','wheels','tyre','tyres','tire','tires','bike','bicycle','cycling',
    'said','says','say','also','one','two','new','use','using','used','would','could','may','can'
}
NODES = ['hookless','safety','safe','pressure','compatibility','compatible','failure','fail','blowout','performance','standard','standards','risk']


def tokens(text: str, remove_stop: bool = False) -> list[str]:
    values = TOKEN_RE.findall((text or '').lower())
    return [t for t in values if not remove_stop or t not in STOPWORDS]


def ngrams(items: list[str], n: int):
    return zip(*(items[i:] for i in range(n)))


def log_ratio(a: int, total_a: int, b: int, total_b: int, smoothing: float = 0.5) -> float:
    return math.log2(((a + smoothing) / (total_a + smoothing)) / ((b + smoothing) / (total_b + smoothing)))


def main() -> None:
    parser = argparse.ArgumentParser(description='Run full-corpus lexical CADS analysis')
    parser.add_argument('sentence_csv', type=Path)
    parser.add_argument('output_directory', type=Path)
    parser.add_argument('--window', type=int, default=5)
    parser.add_argument('--top', type=int, default=100)
    args = parser.parse_args()

    out = args.output_directory
    out.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(args.sentence_csv, encoding='utf-8-sig').fillna('')
    required = {'document_id','source_type','source_name','url','sentence'}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f'Missing columns: {sorted(missing)}')

    docs = (df.groupby(['document_id','source_type','source_name','url'], as_index=False)
              .agg(text=('sentence',' '.join), sentences=('sentence','size')))
    communities = sorted(df['source_type'].unique())

    summary = {
        'documents': int(docs['document_id'].nunique()),
        'sentences': int(len(df)),
        'tokens': int(sum(len(tokens(s)) for s in df['sentence'])),
        'documents_by_community': docs.groupby('source_type')['document_id'].nunique().astype(int).to_dict(),
        'sentences_by_community': df.groupby('source_type').size().astype(int).to_dict(),
    }
    (out / 'cads_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')

    freq_rows, bigram_rows, trigram_rows = [], [], []
    community_counters: dict[str, Counter] = {}
    community_totals: dict[str, int] = {}
    for community in communities:
        text = ' '.join(df.loc[df.source_type == community, 'sentence'])
        raw = tokens(text)
        clean = [t for t in raw if t not in STOPWORDS]
        counter = Counter(clean)
        community_counters[community] = counter
        community_totals[community] = sum(counter.values())
        for term, count in counter.most_common(args.top):
            freq_rows.append({'community': community, 'term': term, 'count': count,
                              'per_10000': count / max(1, len(raw)) * 10000})
        for gram, count in Counter(ngrams(clean, 2)).most_common(args.top):
            bigram_rows.append({'community': community, 'bigram': ' '.join(gram), 'count': count})
        for gram, count in Counter(ngrams(clean, 3)).most_common(args.top):
            trigram_rows.append({'community': community, 'trigram': ' '.join(gram), 'count': count})

    pd.DataFrame(freq_rows).to_csv(out / 'community_frequencies.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(bigram_rows).to_csv(out / 'community_bigrams.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(trigram_rows).to_csv(out / 'community_trigrams.csv', index=False, encoding='utf-8-sig')

    key_rows = []
    global_counter = sum(community_counters.values(), Counter())
    global_total = sum(community_totals.values())
    for community in communities:
        this = community_counters[community]
        this_total = community_totals[community]
        rest = global_counter - this
        rest_total = global_total - this_total
        for term in set(this) | set(rest):
            if this[term] + rest[term] < 5:
                continue
            lr = log_ratio(this[term], this_total, rest[term], rest_total)
            key_rows.append({'community': community, 'term': term, 'count_in_community': this[term],
                             'count_elsewhere': rest[term], 'log_ratio': lr})
    key_df = pd.DataFrame(key_rows)
    key_df['abs_log_ratio'] = key_df['log_ratio'].abs()
    key_df.sort_values(['community','abs_log_ratio'], ascending=[True,False]).drop(columns='abs_log_ratio').to_csv(
        out / 'community_keyness.csv', index=False, encoding='utf-8-sig')

    coll_rows = []
    concordance_rows = []
    for community in communities:
        for _, row in docs.loc[docs.source_type == community].iterrows():
            toks = tokens(row.text)
            for i, tok in enumerate(toks):
                if tok not in NODES:
                    continue
                left = toks[max(0, i-args.window):i]
                right = toks[i+1:i+1+args.window]
                for coll in left + right:
                    if coll not in STOPWORDS and coll != tok:
                        coll_rows.append({'community': community, 'node': tok, 'collocate': coll,
                                          'document_id': row.document_id})
        for node in NODES:
            subset = df[(df.source_type == community) & df.sentence.str.contains(fr'\b{re.escape(node)}\b', case=False, regex=True)]
            for _, r in subset.head(25).iterrows():
                concordance_rows.append({'community': community, 'node': node, 'document_id': r.document_id,
                                         'url': r.url, 'sentence': r.sentence})

    coll_df = pd.DataFrame(coll_rows)
    if not coll_df.empty:
        coll_summary = (coll_df.groupby(['community','node','collocate'])
                        .agg(count=('collocate','size'), document_spread=('document_id','nunique')).reset_index())
        coll_summary = coll_summary[coll_summary['count'] >= 3]
        coll_summary.sort_values(['community','node','count'], ascending=[True,True,False]).to_csv(
            out / 'collocations.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(concordance_rows).to_csv(out / 'concordance_samples.csv', index=False, encoding='utf-8-sig')

    # Document-normalised lexical profiles for robustness.
    profile_terms = sorted(set(NODES + ['innovation','design','testing','experience','manufacturer','uci','etrto','aero','weight']))
    profile_rows = []
    for _, row in docs.iterrows():
        toks = tokens(row.text)
        total = max(1, len(toks))
        record = {'document_id': row.document_id, 'source_type': row.source_type,
                  'source_name': row.source_name, 'url': row.url, 'tokens': total, 'sentences': row.sentences}
        counts = Counter(toks)
        for term in profile_terms:
            record[f'{term}_per_1000'] = counts[term] / total * 1000
        profile_rows.append(record)
    profiles = pd.DataFrame(profile_rows)
    profiles.to_csv(out / 'document_lexical_profiles.csv', index=False, encoding='utf-8-sig')
    profiles.groupby('source_type').mean(numeric_only=True).to_csv(out / 'community_document_normalised_means.csv', encoding='utf-8-sig')

    with pd.ExcelWriter(out / 'cads_analysis.xlsx', engine='openpyxl') as writer:
        pd.DataFrame([summary]).to_excel(writer, sheet_name='Summary', index=False)
        pd.DataFrame(freq_rows).to_excel(writer, sheet_name='Frequencies', index=False)
        pd.DataFrame(bigram_rows).to_excel(writer, sheet_name='Bigrams', index=False)
        pd.DataFrame(trigram_rows).to_excel(writer, sheet_name='Trigrams', index=False)
        key_df.drop(columns='abs_log_ratio').to_excel(writer, sheet_name='Keyness', index=False)
        if not coll_df.empty:
            coll_summary.to_excel(writer, sheet_name='Collocations', index=False)
        pd.DataFrame(concordance_rows).to_excel(writer, sheet_name='Concordances', index=False)
        profiles.to_excel(writer, sheet_name='Document profiles', index=False)

    print(json.dumps(summary, indent=2))
    print(f'Outputs written to: {out}')


if __name__ == '__main__':
    main()
