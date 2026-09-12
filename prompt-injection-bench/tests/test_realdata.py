import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.build_real_dataset import build, read


ROOT = Path(__file__).resolve().parents[1] / 'data/real-v01'


class RealDataTests(unittest.TestCase):
    def test_rebuild_and_source_holdout(self):
        products = build(ROOT)
        for name, rows in products.items():
            self.assertEqual(read(ROOT / name), rows, name)
        dev = products['dev.json']
        test = products['test.json']
        self.assertEqual((len(dev), len(test)), (11, 12))
        self.assertFalse({r['family'] for r in dev} & {r['family'] for r in test})
        for split in ('dev', 'test'):
            parents = {r['id']: r for r in products[split + '.json']}
            for variant in products[split + '-variants.json']:
                self.assertEqual(variant['source_id'], parents[variant['parent_id']]['source_id'])
                self.assertEqual(variant['split'], split)
            self.assertEqual(len(products[split + '-variants.json']), len(parents) * 12)

    def mutate(self, filename, mutation):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'data'
            shutil.copytree(ROOT, target)
            path = target / filename
            value = read(path)
            mutation(value)
            path.write_text(json.dumps(value), encoding='utf-8')
            with self.assertRaises(ValueError):
                build(target)

    def test_page_tampering_rejected(self):
        self.mutate('source-pages/nist-63b4.json', lambda v: v['25'].update(text='forged evidence'))

    def test_source_assignment_drift_rejected(self):
        self.mutate('sources.json', lambda v: v[0].update(split='test'))

    def test_duplicate_objective_rejected(self):
        self.mutate('annotations.json', lambda v: v.append(dict(v[0], id='duplicate')))

    def test_wrong_answer_rejected(self):
        self.mutate('annotations.json', lambda v: v[0].update(answer='unsupported answer'))


if __name__ == '__main__':
    unittest.main()
