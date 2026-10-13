"""Content-addressed snapshot blocks: fixed player shards avoid rewriting pools."""
import gzip
import hashlib
import json


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()


def identity(row):
    if isinstance(row, dict):
        value = row.get('playerId') or row.get('id') or row.get('team') or row.get('owner') or row.get('Week') or row.get('week')
        if value is not None:
            return str(value) + ':' + str(row.get('_team') or '')
    return hashlib.sha256(encode(row)).hexdigest()


def split(payload):
    # A provider check timestamp is metadata; checking again is not a data change.
    stable = {k: v for k, v in payload.items() if k != 'sourceUpdatedAt'}
    layout = {}
    objects = {}

    def block(value):
        raw = encode(value)
        digest = hashlib.sha256(raw).hexdigest()
        packed = gzip.compress(raw, mtime=0)
        if len(packed) > 600_000:
            raise ValueError('PAYLOAD_BLOCK_TOO_LARGE')
        objects[digest] = packed
        return digest

    core = {}
    for field, value in stable.items():
        if not isinstance(value, list) or not value:
            core[field] = value
        elif len(value) < 128:
            layout[field] = {'block': block(value)}
        else:
            buckets = [[] for _ in range(16)]
            order = []
            occurrences = {}
            for row in value:
                base = identity(row)
                count = occurrences.get(base, 0)
                occurrences[base] = count + 1
                key = base + ':' + str(count)
                order.append(key)
                bucket = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % len(buckets)
                buckets[bucket].append([key, row])
            # Sorting within shards keeps hash stability when provider ordering changes.
            layout[field] = {'order': order, 'shards': [block(sorted(b, key=lambda pair: pair[0])) for b in buckets]}
    layout['$core'] = {'block': block(core)}
    return {'format': 'blocks-v2', 'contentHash': hashlib.sha256(encode(stable)).hexdigest(),
            'layout': layout, 'objects': sorted(objects)}, objects


def join(manifest, objects):
    def value(digest):
        return json.loads(gzip.decompress(objects[digest]))
    result = value(manifest['layout']['$core']['block'])
    for field, layout in manifest['layout'].items():
        if field == '$core':
            continue
        if 'block' in layout:
            result[field] = value(layout['block'])
        else:
            rows = {key: row for digest in layout['shards'] for key, row in value(digest)}
            result[field] = [rows[key] for key in layout['order']]
    return result
