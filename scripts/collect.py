"""Public FPL collector. Python standard library only; no credentials."""
import datetime as dt
import html
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SEASON = '2026-27'
MANAGERS = {6349748: 'Pranav', 2031878: 'Drew', 378938: 'Gopal', 6752830: 'Ben', 942123: 'Luca', 7431627: 'Atul & Suraj', 4973768: 'Guto'}
BASE = 'https://fantasy.premierleague.com/api/'

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n')
    tmp.replace(path)

def read(path):
    return json.loads(path.read_text()) if path.exists() else None

def request(endpoint):
    for attempt in range(3):
        try:
            req = urllib.request.Request(BASE + endpoint, headers={'User-Agent': 'WarwickFPLTracker/1.0', 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=20) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 404):
                raise
            if attempt == 2:
                raise
        except (OSError, ValueError):
            if attempt == 2:
                raise
        time.sleep(2 ** (attempt + 1))

def valid_season(data):
    events = data.get('events', [])
    return bool(events) and min(x['deadline_time'] for x in events).startswith('2026-')

class Collector:
    def __init__(self, directory, fetch=request):
        self.directory, self.fetch = Path(directory), fetch
        self.errors = []
        self.blocked = False

    def get(self, key, endpoint, validate=lambda x: True, transform=lambda x: x, frozen=False):
        path = self.directory / (key + '.json')
        old = read(path)
        if frozen and old and old.get('final'):
            return old
        try:
            if self.blocked:
                raise RuntimeError('FPL circuit breaker: earlier endpoint returned HTTP 403/429')
            value = self.fetch(endpoint)
            if not validate(value):
                raise ValueError('Unexpected response schema or season')
            result = {'source': BASE + endpoint, 'fetched_at': now(), 'data': transform(value)}
            write(path, result)
            return result
        except Exception as exc:
            if isinstance(exc, urllib.error.HTTPError) and exc.code in (403, 429):
                self.blocked = True
            self.errors.append({'path': key + '.json', 'error': str(exc), 'last_success': old.get('fetched_at') if old else None})
            return old

    def run(self):
        started = now()
        bootstrap = self.get('bootstrap', 'bootstrap-static/', valid_season)
        # Never mix a different season's player IDs into the archive.
        if not bootstrap or any(e['path'] == 'bootstrap.json' for e in self.errors):
            self.finish(started, [], None)
            return
        events = bootstrap['data']['events']
        released = [e for e in events if e['deadline_time'] <= started]
        latest = max((e['id'] for e in released), default=None)
        self.get('fixtures', 'fixtures/', lambda x: isinstance(x, list))
        # Only the seven configured entries are ever saved; fantasy team names are discarded.
        self.get('standings', 'leagues-classic/2426424/standings/?page_standings=1',
                 lambda x: isinstance(x.get('standings', {}).get('results'), list),
                 lambda x: [{'entry': r['entry'], 'name': MANAGERS[r['entry']], 'rank': r['rank'], 'total': r['total'], 'event_total': r['event_total']}
                            for r in x['standings']['results'] if r['entry'] in MANAGERS])
        for entry in MANAGERS:
            self.get(f'managers/{entry}/history', f'entry/{entry}/history/',
                     lambda x: isinstance(x.get('current'), list),
                     lambda x: {'current': x['current'], 'chips': x.get('chips', [])})
            self.get(f'managers/{entry}/transfers', f'entry/{entry}/transfers/', lambda x: isinstance(x, list))
        for event in released:
            gw = event['id']
            final = bool(event.get('finished') and event.get('data_checked'))
            for entry in MANAGERS:
                key = f'managers/{entry}/gw{gw}'
                result = self.get(key, f'entry/{entry}/event/{gw}/picks/',
                                  lambda x: len(x.get('picks', [])) == 15 and 'entry_history' in x, frozen=True)
                self.mark_final(key, result, final)
            key = f'live/gw{gw}'
            result = self.get(key, f'event/{gw}/live/', lambda x: isinstance(x.get('elements'), list), frozen=True)
            self.mark_final(key, result, final)
        self.finish(started, released, latest)

    def mark_final(self, key, result, final):
        if result and final and not result.get('final') and not any(e['path'] == key + '.json' for e in self.errors):
            result['final'] = True
            write(self.directory / (key + '.json'), result)

    def finish(self, started, events, latest):
        status = {'season': SEASON, 'league_id': 2426424, 'attempted_at': started,
                  'finished_at': now(), 'state': 'degraded' if self.errors else 'ok', 'errors': self.errors,
                  'latest_released_gw': latest, 'managers': MANAGERS,
                  'scope': 'Fixed seven named managers; not dynamic league top seven.'}
        write(self.directory / 'status.json', status)
        build_reports(self.directory, status, events)
        print(json.dumps(status, indent=2))


def compare(old, new):
    if not old or not new:
        return {'available': False, 'reason': 'Both gameweeks need successful picks snapshots.'}
    a, b = old['data']['picks'], new['data']['picks']
    ids_a, ids_b = {p['element'] for p in a}, {p['element'] for p in b}
    captain = lambda picks: next((p['element'] for p in picks if p['is_captain']), None)
    xi = lambda picks: {p['element'] for p in picks if p['position'] <= 11}
    return {'available': True, 'squad_in': sorted(ids_b - ids_a), 'squad_out': sorted(ids_a - ids_b),
            'xi_in': sorted(xi(b) - xi(a)), 'xi_out': sorted(xi(a) - xi(b)),
            'captain_before': captain(a), 'captain_after': captain(b),
            'chip': new['data'].get('active_chip'), 'transfer_cost': new['data']['entry_history'].get('event_transfers_cost'),
            'note': 'Squad changes are not paired transfers. Free Hit may revert next GW; consult transfer history.'}


def build_reports(directory, status, events):
    boot = read(directory / 'bootstrap.json')
    players = {p['id']: p for p in boot['data']['elements']} if boot else {}
    fixtures = read(directory / 'fixtures.json')
    def name(pid):
        return players.get(pid, {}).get('web_name', str(pid))
    reports = []
    for event in events:
        gw = event['id']
        report = {'season': SEASON, 'gw': gw, 'generated_at': now(), 'status': status,
                  'players': {pid: {'name': p['web_name'], 'team': p['team'], 'position': p['element_type']} for pid, p in players.items()},
                  'fixtures': [f for f in (fixtures or {}).get('data', []) if f.get('event') == gw],
                  'fixtures_fetched_at': (fixtures or {}).get('fetched_at'),
                  'live': read(directory / f'live/gw{gw}.json'), 'managers': []}
        lines = [f'# Warwick FPL — GW{gw}', '', f'Season: {SEASON}. Feed status: {status["state"]}. Attempt: {status["attempted_at"]}.',
                 'Check status.json errors and each source timestamp before treating data as fresh. Scores may be provisional.', '']
        for entry, personal_name in MANAGERS.items():
            current = read(directory / f'managers/{entry}/gw{gw}.json')
            previous = read(directory / f'managers/{entry}/gw{gw-1}.json')
            transfers = read(directory / f'managers/{entry}/transfers.json')
            diff = compare(previous, current)
            report['managers'].append({'entry': entry, 'name': personal_name, 'picks': current, 'previous_picks': previous, 'diff': diff,
                                       'transfers_fetched_at': (transfers or {}).get('fetched_at'),
                                       'transfers': None if transfers is None else [t for t in transfers['data'] if t.get('event') == gw],
                                       'history': read(directory / f'managers/{entry}/history.json')})
            lines += [f'## {personal_name}', '']
            if not current:
                lines += ['Picks unavailable — not evidence of no changes.', '']
                continue
            picks = current['data']['picks']
            lines += [f'Picks fetched: {current["fetched_at"]}.',
                      'Starting XI: ' + ', '.join(name(p['element']) for p in picks if p['position'] <= 11),
                      'Bench (order): ' + ', '.join(name(p['element']) for p in sorted(picks, key=lambda x: x['position']) if p['position'] > 11),
                      'Captain: ' + ', '.join(name(p['element']) for p in picks if p['is_captain']),
                      'Vice: ' + ', '.join(name(p['element']) for p in picks if p['is_vice_captain']),
                      f'Chip: {current["data"].get("active_chip") or "none"}. Transfer cost: {current["data"]["entry_history"].get("event_transfers_cost")}.']
            if diff['available']:
                lines += ['Squad in: ' + (', '.join(map(name, diff['squad_in'])) or 'none'),
                          'Squad out: ' + (', '.join(map(name, diff['squad_out'])) or 'none')]
            else:
                lines += ['Previous GW unavailable; changes cannot be established.']
            lines += ['']
        write(directory / f'gw{gw}.json', report)
        (directory / f'gw{gw}.md').write_text('\n\n'.join(lines))
        reports.append(gw)
    # Preserve historical reports during upstream outages; current status is always separate.
    existing = sorted(int(p.stem[2:]) for p in directory.glob('gw*.json'))
    write(directory / 'index.json', {'season': SEASON, 'status': status, 'available_gameweeks': existing,
                                    'usage': 'Read status.json then gwN.md and gwN.json. Never infer no transfers from missing data.'})
    cards = ''.join(f'<li><a href="data/{SEASON}/gw{gw}.md">GW{gw} scouting summary</a> · <a href="data/{SEASON}/gw{gw}.json">structured data</a></li>' for gw in reversed(existing))
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Warwick FPL</title>
<style>body{font:17px/1.6 system-ui;max-width:850px;margin:50px auto;padding:0 24px;background:#101927;color:#e9eff9}a{color:#6fe3c4}h1{font-size:42px}li{margin:14px 0}.status{padding:20px;border:1px solid #63748b;border-radius:12px}small{color:#b6c6d9}</style>
<h1>Warwick FPL</h1><p>2026/27 · Seven managers · Public official FPL data</p>'''
    page += f'<p class="status">Feed: <strong>{status["state"].upper()}</strong><br>Latest attempt: {html.escape(status["attempted_at"])}<br>Endpoint failures: {len(status["errors"])}</p>'
    page += f'<p><a href="data/{SEASON}/status.json">Freshness & errors</a> · <a href="data/{SEASON}/index.json">Feed index</a></p><ul>{cards}</ul>'
    page += '<p>Pranav · Drew · Gopal · Ben · Luca · Atul &amp; Suraj · Guto</p><p>Ask ChatGPT to read this URL and scout a gameweek. It must fetch the feed when asked; there is no permanent live sync.</p><small>Updates requested hourly. Check timestamps: scheduling or FPL access can delay updates. Before a deadline, new picks are unavailable. Historical reports survive failures; consult the current status before using them.</small></html>'
    (directory.parent.parent / 'index.html').write_text(page)

if __name__ == '__main__':
    Collector(ROOT / 'docs' / 'data' / SEASON).run()
