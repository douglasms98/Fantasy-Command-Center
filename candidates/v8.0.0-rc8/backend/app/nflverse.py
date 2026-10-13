"""Shared public NFL facts. League rosters and credentials never leave the Cloud.

Only generic season files are downloaded. Fantasy scores/projections continue to
come from each league's scoring rules; these files add observed usage and draft.
"""
import asyncio
import csv
import io
import math
import time
from datetime import date
import httpx

BASE = 'https://github.com/nflverse/nflverse-data/releases/download'
MAX_DOWNLOAD = 24 * 1024 * 1024
OFFENSE = {'QB', 'RB', 'WR', 'TE', 'K'}


def number(value):
    try:
        result = float(value) if value not in (None, '') and not isinstance(value, bool) else None
        return result if result is not None and math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def code(value):
    return {'LA': 'LAR', 'JAC': 'JAX', 'WSH': 'WAS', 'OAK': 'LV', 'SD': 'LAC'}.get(value, value)


def parse_csv(raw, kind, season=None):
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    required = {
        'players': {'gsis_id', 'espn_id', 'pfr_id', 'position', 'draft_pick'},
        'stats': {'player_id', 'season', 'season_type', 'week', 'carries', 'targets'},
        'snaps': {'pfr_player_id', 'season', 'week', 'offense_snaps', 'offense_pct'},
    }[kind]
    if not required.issubset(reader.fieldnames or []):
        raise ValueError('NFLVERSE_SCHEMA_UNAVAILABLE')
    records = []
    for index, row in enumerate(reader):
        if index >= 150_000:
            raise ValueError('NFLVERSE_TOO_MANY_ROWS')
        if kind == 'players':
            if row.get('position') not in OFFENSE:
                continue
            records.append({k: row.get(v) or '' for k, v in {
                'gsis': 'gsis_id', 'espn': 'espn_id', 'pfr': 'pfr_id', 'pos': 'position',
                'name': 'display_name', 'birthDate': 'birth_date', 'team': 'latest_team',
            }.items()} | {k: number(row.get(v)) for k, v in {
                'draftOverall': 'draft_pick', 'draftYear': 'draft_year', 'draftRound': 'draft_round',
            }.items()})
        else:
            week = number(row.get('week'))
            if number(row.get('season')) != season or week is None or week != int(week) or not 1 <= week <= 18:
                continue
            if row.get('season_type', row.get('game_type', '')) != 'REG':
                continue
            pid = row.get('player_id' if kind == 'stats' else 'pfr_player_id')
            if not pid:
                continue
            fields = {'carries': 'carries', 'targets': 'targets', 'receptions': 'receptions',
                      'rushingYards': 'rushing_yards', 'receivingYards': 'receiving_yards',
                      'passingAttempts': 'attempts'} if kind == 'stats' else {
                          'offenseSnaps': 'offense_snaps', 'offenseSnapShare': 'offense_pct'}
            records.append({'id': pid, 'week': int(week), 'team': code(row.get('team', '')),
                            **{k: number(row.get(v)) for k, v in fields.items()}})
    if not records:
        raise ValueError('NFLVERSE_NO_CONFIRMED_ROWS')
    return records


class Nflverse:
    def __init__(self, store=None):
        self.store = store
        self.cache = {}
        self.locks = {}

    async def dataset(self, client, kind, season):
        key = f'nflverse-v1-{kind}' + ('' if kind == 'players' else f'-{season}')
        ttl = 86400 if kind == 'players' else 14400
        async with self.locks.setdefault(key, asyncio.Lock()):
            cached = self.cache.get(key)
            if cached and time.time() - cached.get('savedEpoch', 0) < ttl:
                return cached['payload']
            if cached is None and self.store:
                try:
                    cached = self.store.public_cache(key)
                except Exception:
                    cached = None
                if cached and time.time() - cached.get('savedEpoch', 0) < ttl:
                    self.cache[key] = cached
                    return cached['payload']
            previous = (cached or {}).get('payload') or {}
            filename = {'players': 'players/players.csv',
                        'stats': f'stats_player/stats_player_week_{season}.csv',
                        'snaps': f'snap_counts/snap_counts_{season}.csv'}[kind]
            headers = {'Accept': 'text/csv', 'Accept-Encoding': 'identity'}
            for field, header in [('etag', 'If-None-Match'), ('lastModified', 'If-Modified-Since')]:
                if previous.get(field):
                    headers[header] = previous[field]
            try:
                # This client has no league cookie, Firebase token or player query.
                async with client.stream('GET', f'{BASE}/{filename}', headers=headers, follow_redirects=True) as response:
                    if response.status_code == 304 and previous.get('records'):
                        payload = {k: v for k, v in previous.items() if k not in ('stale', 'unavailable')}
                    else:
                        response.raise_for_status()
                        data = bytearray()
                        async for chunk in response.aiter_bytes():
                            data.extend(chunk)
                            if len(data) > MAX_DOWNLOAD:
                                raise ValueError('NFLVERSE_DOWNLOAD_TOO_LARGE')
                        records = await asyncio.to_thread(parse_csv, bytes(data), kind, season)
                        payload = {'records': records, 'etag': response.headers.get('etag', ''),
                                   'lastModified': response.headers.get('last-modified', ''), 'source': 'nflverse'}
                self.cache[key] = {'savedEpoch': time.time(), 'payload': payload}
                self.trim_cache(key)
                if self.store:
                    try:
                        self.store.save_public_cache(key, payload)
                    except Exception:
                        pass  # The in-process cache remains usable if storage is unavailable.
                return payload
            except (httpx.HTTPError, ValueError, UnicodeError, csv.Error):
                # Retry after four hours, not on every league/user refresh.
                fallback = {**previous, 'stale': True} if previous.get('records') else {'records': [], 'unavailable': True}
                self.cache[key] = {'savedEpoch': time.time(), 'payload': fallback}
                self.trim_cache(key)
                return fallback

    def trim_cache(self, current):
        if len(self.cache) > 12:
            oldest = min((k for k in self.cache if k != current), key=lambda k: self.cache[k]['savedEpoch'])
            del self.cache[oldest]

    async def get(self, season):
        if not isinstance(season, int) or not 2000 <= season <= 2100:
            raise ValueError('INVALID_NFL_SEASON')
        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
            results = await asyncio.gather(*(self.dataset(client, kind, season) for kind in ('players', 'stats', 'snaps')))
        return dict(zip(('players', 'stats', 'snaps'), results))


def qb_context(directory):
    candidates = {}
    for pid, p in directory.items():
        if p.get('position') == 'QB' and number(p.get('depth_chart_order')) == 1 and p.get('team') and p.get('active') is not False:
            candidates.setdefault(code(p['team']), []).append((pid, p))
    result = {}
    for team, rows in candidates.items():
        if len(rows) != 1:
            continue  # Ambiguous depth charts must not invent a starter.
        pid, p = rows[0]
        injury = str(p.get('injury_status') or '').upper()
        status = 'UNAVAILABLE' if injury in ('OUT', 'IR', 'DOUBTFUL', 'SUSPENDED', 'PUP') else 'QUESTIONABLE' if injury == 'QUESTIONABLE' else 'NO_RESTRICTION_REPORTED'
        result[team] = {'qb1': p.get('full_name') or ' '.join(filter(None, [p.get('first_name'), p.get('last_name')])),
                        'playerId': pid, 'status': status, 'injuryStatus': injury, 'source': 'Sleeper • depth chart'}
    return result


def enrich(league, datasets, directory=None):
    week = int(league.get('sourceAnalysisWeek') or 0)
    lookup = {}
    for row in datasets.get('players', {}).get('records', []):
        for kind in ('espn', 'gsis', 'pfr'):
            if row.get(kind):
                lookup.setdefault((kind, str(row[kind])), []).append(row)
    histories = {}
    snaps = {}
    for kind, target in [('stats', histories), ('snaps', snaps)]:
        for row in datasets.get(kind, {}).get('records', []):
            if 0 < row['week'] < week:
                target.setdefault(row['id'], {})[row['week']] = row
    quarterbacks = qb_context(directory or {})
    matched = {}
    for p in league.get('_allRosters', []) + league.get('roster', []) + league.get('waivers', []):
        pos = p.get('pos')
        if pos not in OFFENSE:
            continue
        key = (str(p.get('espnId') or (p.get('playerId') if league.get('platform') == 'ESPN' else '') or ''), pos)
        if key not in matched:
            rows = lookup.get(('espn', key[0]), [])
            matching = [r for r in rows if r['pos'] == pos]
            matched[key] = matching[0] if len(matching) == 1 else None
        row = matched[key]
        if row:
            p['nflverseId'] = row['gsis']
            p['draftSource'] = 'NFL • nflverse'
            p['draftKnown'] = row.get('draftYear') is not None or row.get('draftOverall') is not None
            for field in ('draftYear', 'draftRound', 'draftOverall'):
                value = row.get(field)
                if value is not None and value > 0:
                    p[field] = int(value)
            if p.get('age') is None:
                try:
                    born = date.fromisoformat(row.get('birthDate', ''))
                    today = date.today()
                    p['age'] = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
                except ValueError:
                    pass
            history = histories.get(row['gsis'], {})
            snap_history = snaps.get(row['pfr'], {})
            weeks = sorted(set(history) | set(snap_history))[-3:]
            records = []
            for w in weeks:
                records.append({'week': w, **{k: v for k, v in history.get(w, {}).items() if k not in ('id', 'week')},
                                **{k: v for k, v in snap_history.get(w, {}).items() if k not in ('id', 'week', 'team')}})
            if records:
                p['usageFacts'] = {'season': league.get('season'), 'throughWeek': max(weeks), 'games': records, 'source': 'nflverse'}
                # Same observed-volume scale used by the roster analysis. Missing
                # measurements remain null and are never substituted by zero.
                fields = ('carries', 'receptions', 'targets', 'rushingYards', 'receivingYards')
                measured = [r for r in records if all(r.get(f) is not None for f in fields)]
                if measured and pos in ('RB', 'WR', 'TE'):
                    weights = (2.2, 5, 2, .25, .18)
                    p['usageScore'] = round(max(0, min(100, sum(sum(r[f] * weight for f, weight in zip(fields, weights)) for r in measured) / len(measured))), 1)
                known_snaps = [r for r in records if r.get('offenseSnapShare') is not None]
                if known_snaps:
                    p['snapShare'] = round(sum(r['offenseSnapShare'] for r in known_snaps) / len(known_snaps), 4)
        if pos in ('WR', 'TE') and code(p.get('nfl')) in quarterbacks:
            p['qbContext'] = quarterbacks[code(p['nfl'])]
    eligible = [p for p in league.get('roster', []) if p.get('pos') in OFFENSE]
    receivers = [p for p in eligible if p.get('pos') in ('WR', 'TE')]
    league['enrichmentCoverage'] = {
        'eligible': len(eligible), 'usage': sum(bool(p.get('usageFacts')) for p in eligible),
        'snaps': sum(p.get('snapShare') is not None for p in eligible),
        'draft': sum(bool(p.get('draftKnown')) for p in eligible),
        'qbEligible': len(receivers), 'qbContext': sum(bool(p.get('qbContext')) for p in receivers),
        'throughWeek': max([p.get('usageFacts', {}).get('throughWeek', 0) for p in eligible] + [0]),
        'source': 'nflverse + Sleeper', 'stale': any(d.get('stale') for d in datasets.values()),
        'unavailable': [k for k, d in datasets.items() if d.get('unavailable')],
    }
    return league
