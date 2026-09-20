"""Candidate defense: local span quarantine plus a literal citation gate.

Only runtime input/output is accepted. Gold answers and attack markers are not inputs.
This heuristic is not a semantic instruction detector or entailment verifier.
"""
import json
import re


def quarantine(chunks, rules):
    kept, edits = [], []
    for index, chunk in enumerate(chunks):
        # Keep original spans; splitting decimals/abbreviations is imperfect.
        spans = list(re.finditer(r'.+?(?:[。！？]|[.!?](?=\s|$)|\n|$)', chunk, re.S))
        safe, rejected, pending = [], [], []
        for match in spans:
            text = match.group()
            hits = [rule for rule in rules if re.search(rule, text, re.I)]
            if hits:
                if pending:
                    safe.append(''.join(pending))
                    pending = []
                rejected.append(dict(start=match.start(), end=match.end(), text=text, rules=hits))
            else:
                pending.append(text)
        if pending:
            safe.append(''.join(pending))
        # Separate retained spans: never create a new citation by joining across a deletion.
        kept.extend(text for text in safe if text.strip())
        if rejected:
            edits.append(dict(index=index, text=chunk, rules=sorted({r for s in rejected for r in s['rules']}),
                              full_chunk=not any(s.strip() for s in safe), spans=rejected))
    return kept, edits


def citation_gate(text, retained):
    candidate = text.strip()
    fence = re.fullmatch(r'```(?:json)?\s*\n(.*?)\n```', candidate, re.S | re.I)
    if fence:
        candidate = fence.group(1).strip()
    try:
        value = json.loads(candidate)
    except (ValueError, TypeError):
        value = None
    valid = isinstance(value, dict) and all(isinstance(value.get(k), str) for k in ('answer', 'evidence'))
    reason = None
    if not valid:
        reason = 'invalid_schema'
    elif value['answer'].strip().upper() == 'UNKNOWN':
        # Do not present an unsupported explanation as a source quotation.
        return json.dumps(dict(answer='UNKNOWN', evidence='')), dict(blocked=False, reason='model_abstained')
    elif not value['evidence'].strip() or not any(value['evidence'] in span for span in retained):
        reason = 'citation_not_in_retained_span'
    if reason:
        return json.dumps(dict(answer='UNKNOWN', evidence='')), dict(blocked=True, reason=reason)
    return text, dict(blocked=False, reason='literal_citation_passed')
