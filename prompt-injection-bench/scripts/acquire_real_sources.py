import concurrent.futures
import datetime
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import pypdf

root = Path('data/real-v01')
cache = Path('runs/real-source-pdfs')
cache.mkdir(parents=True, exist_ok=True)
plan = json.loads((root/'split-plan.json').read_text(encoding='utf-8'))

def acquire(source):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(source['pdf_url'], headers={'User-Agent':'Mozilla/5.0 (compatible; research-dataset-builder)'})
    with opener.open(request, timeout=90) as response:
        raw = response.read()
        resolved = response.url
    if not raw.startswith(b'%PDF'):
        raise ValueError('Not a PDF')
    (cache/(source['id']+'.pdf')).write_bytes(raw)
    reader = pypdf.PdfReader(io.BytesIO(raw))
    pages = [' '.join((page.extract_text() or '').split()) for page in reader.pages]
    out = dict(source, retrieved_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), resolved_url=resolved,
               pdf_sha256=hashlib.sha256(raw).hexdigest(), extractor='pypdf '+pypdf.__version__,
               normalization='collapse Unicode whitespace to single ASCII spaces; no translation', pages=pages)
    (cache/(source['id']+'.json')).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'id':source['id'],'pages':len(pages),'bytes':len(raw)}

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    for result in pool.map(acquire, plan['sources']):
        print(json.dumps(result),flush=True)
