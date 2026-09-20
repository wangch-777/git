"""合成5万/30万行，独立进程测量旧/新查询逻辑的耗时和Python分配峰值。"""
import argparse
import json
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

import pandas as pd
from backend.app.services.detection import result_page, statistics, stream_result
from ml.cli import ROOT, write_json


def measure(path, rows, operation):
    # 生成规则：每3行一个攻击，总数来自摘要；计时不含进程启动、数据生成。
    attack = (rows + 2) // 3
    tracemalloc.start()
    started = time.perf_counter()
    if operation.startswith('old'):
        frame = pd.read_csv(path)
        if 'filtered' in operation:
            frame = frame.loc[frame.predicted_label == 1]
        if 'stats' in operation:
            count = int(frame.predicted_label.sum())
            result = statistics(len(frame) - count, count)
        elif 'export' in operation:
            result = len(frame.to_csv(index=False).encode('utf-8-sig'))
        else:
            page = 1 if 'first' in operation else max(1, (len(frame) + 19) // 20)
            result = {'total': len(frame), 'items': frame.iloc[(page-1)*20:page*20].to_dict('records')}
    elif 'stats' in operation:
        result = statistics(rows - attack, attack)
    elif 'export' in operation:
        result = sum(len(chunk) for chunk in stream_result(path, 1 if 'filtered' in operation else None))
    else:
        label = 1 if 'filtered' in operation else None
        total = attack if label == 1 else rows
        page = 1 if 'first' in operation else max(1, (total + 19) // 20)
        result = result_page(path, total, page, 20, label)
    seconds = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {'rows': rows, 'operation': operation, 'seconds': seconds, 'peak_mib': peak / 1024**2,
            'returned': len(result['items']) if isinstance(result, dict) and 'items' in result else result}


def main():
    parser = argparse.ArgumentParser(description='大文件查询性能对比')
    parser.add_argument('--measure', choices=['stats', 'first', 'last', 'filtered-last', 'export', 'filtered-export'])
    parser.add_argument('--old', action='store_true')
    parser.add_argument('--rows', type=int)
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/query-benchmark')
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / 'artifacts').resolve()):
        parser.error('输出必须位于artifacts目录')
    if args.measure:
        result = measure(output / f'{args.rows}.csv', args.rows, ('old-' if args.old else 'new-') + args.measure)
        print(json.dumps(result))
        return
    output.mkdir(parents=True, exist_ok=True)
    all_results = []
    for count in (50000, 300000):
        frame = pd.DataFrame({'source_row_id': range(count), 'predicted_label': [int(i % 3 == 0) for i in range(count)]})
        frame['predicted_name'] = frame.predicted_label.map({0: '正常', 1: '攻击'})
        frame['score'] = .875
        frame.to_csv(output / f'{count}.csv', index=False, encoding='utf-8-sig')
        del frame
        for operation in ('stats', 'first', 'last', 'filtered-last', 'export', 'filtered-export'):
            for old in (True, False):
                values = []
                for repeat in range(3):
                    command = [sys.executable, '-m', 'ml.benchmark_queries', '--measure', operation,
                               '--rows', str(count), '--output', str(output)] + (['--old'] if old else [])
                    values.append(json.loads(subprocess.check_output(command, text=True)))
                import statistics as stats
                value = {**values[0], 'seconds': stats.median(x['seconds'] for x in values),
                         'peak_mib': stats.median(x['peak_mib'] for x in values)}
                all_results.append(value)
                write_json(output / 'results.json', all_results)
                print(json.dumps(value), flush=True)


if __name__ == '__main__':
    main()
