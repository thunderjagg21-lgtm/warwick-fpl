import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from collect import Collector, compare, valid_season, write, read, MANAGERS

def picks(ids):
    return {'data': {'picks': [{'element': i, 'position': n + 1, 'is_captain': n == 0, 'is_vice_captain': n == 1} for n, i in enumerate(ids)], 'entry_history': {'event_transfers_cost': 4}, 'active_chip': None}}

class Tests(unittest.TestCase):
    def test_changes_and_captain(self):
        a, b = picks(range(1, 16)), picks(range(2, 17))
        d = compare(a, b)
        self.assertEqual(d['squad_in'], [16])
        self.assertEqual(d['squad_out'], [1])
        self.assertEqual(d['captain_after'], 2)
        self.assertEqual(d['transfer_cost'], 4)
        self.assertFalse(compare(None, b)['available'])

    def test_block_preserves_last_good_and_stops_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = {'fetched_at': 'old', 'data': [1]}
            write(Path(tmp) / 'picks.json', old)
            calls = []
            def blocked(endpoint):
                calls.append(endpoint)
                raise urllib.error.HTTPError(endpoint, 403, 'Forbidden', {}, None)
            c = Collector(tmp, blocked)
            self.assertEqual(c.get('picks', 'x'), old)
            self.assertIsNone(c.get('other', 'y'))
            self.assertEqual(len(calls), 1)
            self.assertEqual(read(Path(tmp) / 'picks.json'), old)
            self.assertEqual(len(c.errors), 2)

    def test_final_snapshot_skips_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(Path(tmp) / 'picks.json', {'final': True, 'data': []})
            c = Collector(tmp, lambda _: self.fail('Frozen snapshot fetched again'))
            self.assertTrue(c.get('picks', 'x', frozen=True)['final'])

    def test_season_guard(self):
        self.assertFalse(valid_season({'events': [{'deadline_time': '2025-08-10'}]}))
        self.assertTrue(valid_season({'events': [{'deadline_time': '2026-08-10'}]}))

    def test_complete_run_filters_names_and_future_weeks(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / 'docs/data/2026-27'
            directory.mkdir(parents=True)
            calls = []
            def fetch(endpoint):
                calls.append(endpoint)
                if endpoint == 'bootstrap-static/':
                    return {'events': [{'id': 1, 'deadline_time': '2026-01-01', 'finished': True, 'data_checked': True}, {'id': 2, 'deadline_time': '2099-01-01'}], 'elements': []}
                if endpoint == 'fixtures/': return []
                if endpoint.startswith('leagues-'):
                    return {'standings': {'results': [{'entry': 6349748, 'entry_name': 'DO NOT PUBLISH', 'rank': 1, 'total': 100, 'event_total': 20}, {'entry': 999, 'rank': 2, 'total': 90, 'event_total': 10}]}}
                if endpoint.endswith('history/'): return {'current': [], 'chips': [], 'past': []}
                if endpoint.endswith('transfers/'): return []
                if endpoint.endswith('live/'): return {'elements': []}
                return picks(range(1, 16))['data']
            c = Collector(directory, fetch)
            c.run()
            self.assertEqual(read(directory / 'status.json')['state'], 'ok')
            report = read(directory / 'gw1.json')
            self.assertEqual(len(report['managers']), 7)
            self.assertFalse(any('/event/2/' in x for x in calls))
            self.assertNotIn('DO NOT PUBLISH', (directory / 'standings.json').read_text())
            self.assertEqual(len(read(directory / 'standings.json')['data']), 1)
            self.assertTrue(read(directory / 'managers/6349748/gw1.json')['final'])
            # A season mismatch must leave the old reports intact.
            previous = (directory / 'gw1.json').read_text()
            Collector(directory, lambda _: {'events': []}).run()
            self.assertEqual((directory / 'gw1.json').read_text(), previous)
            self.assertEqual(read(directory / 'status.json')['state'], 'degraded')

if __name__ == '__main__': unittest.main()
