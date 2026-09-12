import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from argparse import Namespace

from bench.identity import model_digests, verify
from bench.__main__ import freeze, run, source_hash
from bench.data import digest, seeds


class IdentityTests(unittest.TestCase):
    def inventory(self, rows):
        context = unittest.mock.MagicMock()
        context.__enter__.return_value.read.return_value = json.dumps({'models': rows}).encode()
        return context

    def test_full_digest_and_exact_tag(self):
        with patch('urllib.request.urlopen', return_value=self.inventory([{'name':'m:tag','digest':'a'*64}])):
            self.assertEqual(model_digests('http://local', ['m:tag'], 1), {'m:tag':'a'*64})
            with self.assertRaises(ValueError):
                model_digests('http://local', ['m'], 1)

    def test_cloud_short_and_missing_digests_rejected(self):
        for row in ({'name':'m','digest':'a'*12}, {'name':'m'},
                    {'name':'m','digest':'a'*64,'remote_host':'https://remote'}):
            with patch('urllib.request.urlopen', return_value=self.inventory([row])):
                with self.assertRaises(ValueError):
                    model_digests('http://local', ['m'], 1)

    def test_matching_mismatch_legacy_and_mock(self):
        config = dict(provider='ollama', models=['m'], endpoint='http://local', timeout=1, model_digests={'m':'a'*64})
        with patch('bench.identity.model_digests', return_value={'m':'a'*64}):
            self.assertEqual(verify(config)['status'], 'verified')
        with patch('bench.identity.model_digests', return_value={'m':'b'*64}):
            with self.assertRaises(ValueError):
                verify(config)
        config.pop('model_digests')
        with self.assertRaisesRegex(ValueError, 'legacy'):
            verify(config)
        self.assertEqual(verify({'provider':'mock'})['status'], 'mock_not_applicable')

    def test_precheck_stops_before_inference_and_output_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = dict(provider='ollama', models=['m'], endpoint='http://local', timeout=1,
                          dataset=seeds(), dataset_sha256=digest(seeds()), code_sha256=source_hash(), model_digests={'m':'a'*64})
            lock = root/'lock.json'
            lock.write_text(json.dumps({'config':config,'sha256':digest(config)}), encoding='utf-8')
            with patch('bench.identity.model_digests', return_value={'m':'b'*64}), patch('bench.__main__.OllamaProvider') as provider:
                with self.assertRaisesRegex(ValueError, 'mismatch'):
                    run(Namespace(lock=str(lock), out=str(root/'out')))
                provider.assert_not_called()
                self.assertFalse((root/'out').exists())

    def test_postcheck_marks_changed_model_and_keeps_logs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root/'data.json'
            data.write_text(json.dumps(seeds()[:1]), encoding='utf-8')
            args = Namespace(dataset=str(data), split='dev', repeats=1, timeout=1, temperature=0,
                             models=['m'], provider='ollama', endpoint='http://local', seed=1,
                             digest=[], out=str(root/'lock.json'))
            with patch('bench.__main__.model_digests', return_value={'m':'a'*64}):
                freeze(args)
            with patch('bench.identity.model_digests', side_effect=[{'m':'a'*64},{'m':'b'*64}]), patch('bench.__main__.OllamaProvider') as provider:
                provider.return_value.complete.return_value = {'text':'UNKNOWN'}
                with self.assertRaisesRegex(ValueError, 'Post-run'):
                    run(Namespace(lock=args.out, out=str(root/'out')))
            state = json.loads((root/'out/model-verification.json').read_text())
            self.assertEqual(state['status'], 'failed_postcheck')
            self.assertEqual(len((root/'out/results.jsonl').read_text(encoding='utf-8').splitlines()), 12)
