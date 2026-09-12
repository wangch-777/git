"""Offline, deterministic build from checked-in source excerpts and annotations."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bench.data import cases, validate


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def build(root):
    plan = read(root / 'split-plan.json')
    registry = {s['id']: s for s in read(root / 'sources.json')}
    if set(registry) != {s['id'] for s in plan['sources']}:
        raise ValueError('Source registry membership disagrees with split plan')
    assignments = {}
    for source in plan['sources']:
        previous = assignments.setdefault(source['family'], source['split'])
        if previous != source['split']:
            raise ValueError('Publication family crosses splits')
        if any(registry[source['id']][k] != v for k, v in source.items()):
            raise ValueError('Source registry disagrees with split plan')
    rows, objectives = [], set()
    for a in read(root / 'annotations.json'):
        s = registry[a['source_id']]
        objective = (s['family'], a['objective'])
        if objective in objectives:
            raise ValueError('Repeated learning objective')
        objectives.add(objective)
        page = read(root / 'source-pages' / (s['id'] + '.json'))[str(a['page'])]
        if sha(page['text']) != page['sha256']:
            raise ValueError('Source page digest mismatch')
        text = page['text']
        if text.count(a['start']) != 1:
            raise ValueError('Ambiguous or missing start: ' + a['id'])
        start = text.index(a['start'])
        end = text.index(a['end'], start) + len(a['end'])
        evidence = text[start:end]
        rows.append(dict(id='real-' + a['id'], family=s['family'], source_id=s['id'],
                         split=s['split'], question=a['question'], answer=a['answer'],
                         answer_aliases=a['aliases'], evidence=evidence,
                         benign_note='请依据所给文档片段回答。', expanded=True,
                         provenance='Real NIST document excerpt; AI-authored question and synthetic variants; independent human review pending.',
                         dataset_kind='real_document', objective=a['objective'],
                         source_url=s['landing_url'], license=s['license'],
                         evidence_locator=dict(pdf_page_1based=a['page'], section=a['section'],
                                               start_offset=start, end_offset=end, page_sha256=page['sha256']),
                         annotation_status='AI_checked_human_review_pending',
                         question_language='zh', evidence_language='en'))
    validate(rows)
    if len({r['question'] for r in rows}) != len(rows):
        raise ValueError('Duplicate question')
    output = {'dataset.json': rows}
    for split in ('dev', 'test'):
        output[split + '.json'] = [r for r in rows if r['split'] == split]
        output[split + '-variants.json'] = [dict(case_id=c['case_id'], parent_id=c['id'],
             source_id=c['source_id'], split=c['split'], variant=c['variant'], language=c['language'],
             chunks_sha256=sha(json.dumps(c['chunks'], ensure_ascii=False))) for c in cases(rows, split)]
    # Before inference: one distinct question per development publication; no outcome-based selection.
    ids = {'real-auth-length', 'real-cloud-iaas', 'real-zt-policyengine'}
    output['pilot-dev.json'] = [r for r in rows if r['id'] in ids and r['split'] == 'dev']
    if len(output['pilot-dev.json']) != 3:
        raise ValueError('Pilot selection incomplete')
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    root = ROOT / 'data/real-v01'
    for name, value in build(root).items():
        path = root / name
        if args.check:
            if read(path) != value:
                raise ValueError('Generated data drift: ' + name)
        else:
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Real dataset and variants verified' if args.check else 'Real dataset and variants built')


if __name__ == '__main__':
    main()
