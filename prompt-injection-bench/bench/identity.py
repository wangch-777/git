"""Verify Ollama's full local manifest digest, not its mutable display name."""
import json
import re
import urllib.request


def model_digests(endpoint, models, timeout):
    with urllib.request.urlopen(endpoint.rstrip('/') + '/api/tags', timeout=timeout) as response:
        inventory = json.load(response)
    entries = inventory.get('models')
    if not isinstance(entries, list):
        raise ValueError('Invalid Ollama model inventory')
    result = {}
    for name in models:
        matches = [m for m in entries if m.get('name') == name]
        if len(matches) != 1:
            raise ValueError(f'Model missing or ambiguous: {name}; use its exact installed tag')
        model = matches[0]
        if model.get('remote_host') or model.get('remote_model'):
            raise ValueError(f'Cloud model digest cannot pin remote weights: {name}')
        value = model.get('digest', '')
        if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
            raise ValueError(f'Missing full SHA256 digest: {name}')
        result[name] = value
    return result


def verify(config):
    if config['provider'] == 'mock':
        return {'status': 'mock_not_applicable', 'digests': {}}
    expected = config.get('model_digests')
    if not isinstance(expected, dict) or set(expected) != set(config['models']):
        raise ValueError('Unpinned legacy lock: freeze a new experiment with model digests')
    actual = model_digests(config['endpoint'], config['models'], config['timeout'])
    if actual != expected:
        raise ValueError('Model digest mismatch; stop and freeze a new experiment intentionally')
    return {'status': 'verified', 'digests': actual}
