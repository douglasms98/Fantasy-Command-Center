import gzip
import json
import hashlib
import threading
import time
from collections import OrderedDict
from .payload_blocks import split, join
from datetime import datetime, timezone, timedelta
import secrets
from uuid import uuid4
from google.cloud import firestore
from .config import settings, MAX_LEAGUES_PER_USER

def now():
    return datetime.now(timezone.utc).isoformat()

# Immutable payloads stay scoped by UID, league, binding generation and revision.
# Shared across Store instances, bounded in bytes and entries; never an auth cache.
_PAYLOAD_CACHE = OrderedDict()
_CACHE_BYTES = 0
_CACHE_LOCK = threading.Lock()


def cache_payload(key, payload=None):
    global _CACHE_BYTES
    with _CACHE_LOCK:
        if payload is None:
            entry = _PAYLOAD_CACHE.get(key)
            if entry and time.monotonic() - entry[0] < 300:
                _PAYLOAD_CACHE.move_to_end(key)
                return json.loads(gzip.decompress(entry[1]))
            return None
        packed = gzip.compress(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode(), mtime=0)
        old = _PAYLOAD_CACHE.pop(key, None)
        if old:
            _CACHE_BYTES -= len(old[1])
        _PAYLOAD_CACHE[key] = (time.monotonic(), packed)
        _CACHE_BYTES += len(packed)
        while len(_PAYLOAD_CACHE) > 32 or _CACHE_BYTES > 32 * 1024 * 1024:
            _, entry = _PAYLOAD_CACHE.popitem(last=False)
            _CACHE_BYTES -= len(entry[1])


class Store:
    """All private data is reached through the UID from a verified token."""
    def __init__(self):
        s = settings()
        self.db = firestore.Client(project=s.FCC_GCP_PROJECT, database=s.FCC_FIRESTORE_DATABASE)

    def user(self, uid):
        return self.db.collection('fcc_users').document(uid)

    def league(self, uid, lid):
        return self.user(uid).collection('leagues').document(lid)

    def profile(self, uid, email):
        self.user(uid).set({'uid': uid, 'email': email, 'lastSeenAt': now()}, merge=True)

    def google_challenge(self, transport, purpose, owner_uid=''):
        challenge_id=secrets.token_hex(32)
        nonce=secrets.token_urlsafe(32)
        expires=datetime.now(timezone.utc)+timedelta(minutes=5)
        self.db.collection('fcc_auth_challenges').document(challenge_id).create({
            'transport':transport,'purpose':purpose,'ownerUid':owner_uid,
            'nonce':nonce,'expiresAt':expires})
        return {'challengeId':challenge_id,'nonce':nonce,'expiresIn':300}

    def consume_google_challenge(self, challenge_id, transport, purpose, owner_uid=''):
        ref=self.db.collection('fcc_auth_challenges').document(challenge_id)
        tx=self.db.transaction()
        @firestore.transactional
        def consume(transaction):
            row=ref.get(transaction=transaction).to_dict()
            if not row or row.get('transport')!=transport or row.get('purpose')!=purpose or row.get('ownerUid')!=owner_uid:
                return None
            expiry=row.get('expiresAt')
            if not isinstance(expiry,datetime) or expiry<=datetime.now(timezone.utc):return None
            transaction.delete(ref)
            return row
        return consume(tx)

    def list_leagues(self, uid):
        return [dict(d.to_dict(), id=d.id) for d in self.user(uid).collection('leagues').stream()]

    def get(self, uid, lid):
        d = self.league(uid, lid).get()
        return dict(d.to_dict(), id=d.id) if d.exists else None

    def put(self, uid, lid, row):
        # update cannot resurrect a league removed while the provider was loading.
        self.league(uid, lid).update(row)

    def update_binding(self, uid, lid, version, row):
        ref=self.league(uid,lid)
        tx=self.db.transaction()
        @firestore.transactional
        def update(transaction):
            current=ref.get(transaction=transaction).to_dict()
            if not current or current.get('bindingVersion')!=version:return False
            transaction.update(ref,row)
            return True
        return update(tx)

    def claim_sync(self, uid, lid, seconds):
        import time
        ref=self.league(uid,lid)
        tx=self.db.transaction()
        @firestore.transactional
        def claim(transaction):
            row=ref.get(transaction=transaction).to_dict()
            if not row:return False
            if time.time()-float(row.get('lastAttemptEpoch',0))<seconds:return False
            transaction.update(ref,{'lastAttemptEpoch':time.time(),'lastAttemptAt':now()})
            return True
        return claim(tx)

    def credentials(self,uid,lid,secret):
        # UID/lid are part of the approved secret namespace. Users cannot set this field.
        expected=f'fcc-espn-{uid}-{lid}'
        if secret!=expected:raise ValueError('INVALID_CREDENTIAL_BINDING')
        from google.cloud import secretmanager
        import json
        name=f'projects/{settings().FCC_GCP_PROJECT}/secrets/{secret}/versions/latest'
        raw=secretmanager.SecretManagerServiceClient().access_secret_version(request={'name':name}).payload.data
        body=json.loads(raw)
        return {'SWID':body['SWID'],'espn_s2':body['espn_s2']}

    def create(self, uid, lid, row):
        # The parent user acts as the contention point for concurrent quota checks.
        transaction = self.db.transaction()
        @firestore.transactional
        def create_tx(tx):
            ref = self.user(uid)
            profile = ref.get(transaction=tx).to_dict() or {}
            existing = self.league(uid, lid).get(transaction=tx)
            if existing.exists:
                return False
            count = int(profile.get('leagueCount', 0))
            if count >= MAX_LEAGUES_PER_USER:
                return None
            tx.set(self.league(uid, lid), row)
            tx.set(ref, {'leagueCount': count + 1}, merge=True)
            return True
        return create_tx(transaction)

    def remove(self, uid, lid):
        old_revisions=list(self.league(uid,lid).collection('revisions').stream())
        old_blocks=list(self.league(uid,lid).collection('blocks').stream())
        transaction = self.db.transaction()
        @firestore.transactional
        def remove_tx(tx):
            ref = self.league(uid, lid)
            doc = ref.get(transaction=tx)
            user = self.user(uid)
            profile = user.get(transaction=tx).to_dict() or {}
            if not doc.exists:
                return False
            tx.delete(ref)
            tx.set(user, {'leagueCount': max(0, int(profile.get('leagueCount', 0)) - 1)}, merge=True)
            return True
        removed = remove_tx(transaction)
        if removed:
            # Delete only retired revisions: a concurrent re-registration must survive.
            for old in old_revisions:
                self.db.recursive_delete(old.reference)
            for old in old_blocks:
                old.reference.delete()
        return removed

    def save_payload(self, uid, lid, payload, version):
        root = self.league(uid, lid)
        current = self.get(uid, lid)
        if not current or current.get('bindingVersion') != version:
            return False
        manifest, objects = split(payload)
        old = {}
        if current.get('revision'):
            old = root.collection('revisions').document(current['revision']).get().to_dict() or {}
        checked = now()
        metadata = {'lastCheckedAt': checked, 'lastSuccessAt': checked, 'status': 'ready', 'lastError': '',
                    'sourceAnalysisWeek': int(payload.get('sourceAnalysisWeek') or 0)}
        if old.get('contentHash') == manifest['contentHash'] and old.get('format') == 'blocks-v2':
            if not self.update_binding(uid, lid, version, {**metadata, 'syncChangedBlocks': 0}):
                return False
            if time.time() - float(current.get('blocksGcEpoch') or 0) >= 86400:
                self.collect_payloads_safely(uid, lid, version)
            return {'changed': False, 'changedBlocks': 0, 'totalBlocks': len(objects)}
        revision = uuid4().hex
        generation = hashlib.sha256(str(version).encode()).hexdigest()[:24]
        # Reuse only objects referenced by the current immutable revision. Other
        # generations and retired objects are written afresh, including their age.
        reused = set(old.get('objects', [])) if old.get('generation') == generation else set()
        changed = set(objects) - reused
        batch = self.db.batch()
        for digest in sorted(changed):
            batch.set(root.collection('blocks').document(generation + '_' + digest),
                      {'data': objects[digest], 'createdEpoch': time.time(), 'generation': generation})
        manifest.update(createdAt=checked, generation=generation, bindingVersion=version)
        batch.set(root.collection('revisions').document(revision), manifest)
        batch.commit()
        if not self.update_binding(uid, lid, version, {**metadata, 'revision': revision,
                                                       'lastChangedAt': checked, 'syncChangedBlocks': len(changed)}):
            self.db.recursive_delete(root.collection('revisions').document(revision))
            # A removed/re-added binding uses a different namespace. Never delete
            # objects belonging to its new generation.
            for digest in changed:
                root.collection('blocks').document(generation + '_' + digest).delete()
            return False
        cache_payload((uid, lid, version, revision), {k: v for k, v in payload.items() if k != 'sourceUpdatedAt'})
        if time.time() - float(current.get('blocksGcEpoch') or 0) >= 86400:
            self.collect_payloads_safely(uid, lid, version)
        return {'changed': True, 'changedBlocks': len(changed), 'totalBlocks': len(objects)}

    def collect_payloads_safely(self, uid, lid, version):
        try:
            self.collect_payloads(uid, lid, version)
        except Exception:
            # Cleanup cannot turn a successfully published snapshot into an error.
            # Schedule a retry on the next sync without revealing private content.
            try:
                self.update_binding(uid, lid, version, {'blocksGcEpoch': 0})
            except Exception:
                pass

    def collect_payloads(self, uid, lid, version):
        root = self.league(uid, lid)
        current = self.get(uid, lid)
        if not current or current.get('bindingVersion') != version:
            return
        if not self.update_binding(uid, lid, version, {'blocksGcEpoch': time.time()}):
            return
        live = set()
        for old in root.collection('revisions').stream():
            info = old.to_dict() or {}
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(info.get('createdAt', ''))).total_seconds()
            except (ValueError, TypeError):
                age = 0  # Unrecognized legacy metadata must not trigger deletion.
            if old.id != current.get('revision') and age > 86400:
                self.db.recursive_delete(old.reference)
            else:
                live.update(info.get('generation', '') + '_' + digest for digest in info.get('objects', []))
        # New blocks and their manifest are committed together. Every reused
        # block belongs to the current/recent manifests retained above.
        for block in root.collection('blocks').stream():
            info = block.to_dict() or {}
            if block.id not in live and time.time() - float(info.get('createdEpoch') or time.time()) > 86400:
                block.reference.delete()

    def read_payload(self, uid, lid, row):
        rev = row.get('revision')
        if not rev:
            return None
        key = (uid, lid, row.get('bindingVersion'), rev)
        cached = cache_payload(key)
        if cached is not None:
            return cached
        root = self.league(uid, lid)
        ref = root.collection('revisions').document(rev)
        info = ref.get().to_dict() or {}
        try:
            if info.get('format') == 'blocks-v2':
                if info.get('bindingVersion') != row.get('bindingVersion'):
                    return None
                generation = info['generation']
                refs = [root.collection('blocks').document(generation + '_' + digest) for digest in info['objects']]
                objects = {d.id[len(generation) + 1:]: (d.to_dict() or {})['data'] for d in self.db.get_all(refs)}
                payload = join(info, objects)
            else:
                # Existing Cloud data remains readable; the next sync migrates it.
                if not info.get('chunks'):
                    return None
                packed = b''.join((ref.collection('chunks').document(str(i)).get().to_dict() or {})['data']
                                  for i in range(int(info['chunks'])))
                payload = json.loads(gzip.decompress(packed))
            cache_payload(key, payload)
            return payload
        except (KeyError, OSError, ValueError, TypeError):
            current = self.get(uid, lid)
            if current and current.get('bindingVersion') == row.get('bindingVersion') and current.get('revision') and current['revision'] != rev:
                return self.read_payload(uid, lid, current)
            return None

    def throttle(self, key, limit, seconds):
        import time
        bucket = int(time.time()) // seconds
        ref = self.db.collection('fcc_rate_limits').document(f'{key}_{bucket}')
        tx = self.db.transaction()
        @firestore.transactional
        def check(transaction):
            d = ref.get(transaction=transaction).to_dict() or {}
            count = int(d.get('count', 0))
            if count >= limit:
                return False
            transaction.set(ref, {'count': count + 1, 'expiresAt': datetime.fromtimestamp((bucket + 2) * seconds, timezone.utc)})
            return True
        return check(tx)

    def enabled_bindings(self):
        # Worker IAM identity only; never exposed as a user endpoint.
        for profile in self.db.collection('fcc_users').stream():
            for row in self.list_leagues(profile.id):
                if row.get('enabled', True):
                    yield profile.id, row

    def public_cache(self,key):
        row=self.db.collection('fcc_public_cache').document(key).get().to_dict()
        if row and row.get('payloadGzip'):
            row['payload']=json.loads(gzip.decompress(row['payloadGzip']))
        return row

    def save_public_cache(self,key,payload):
        import time
        raw=json.dumps(payload,separators=(',',':'),ensure_ascii=False).encode('utf-8')
        stable={k:v for k,v in payload.items() if k!='generatedAt'}
        row={'savedEpoch':time.time(),'contentHash':hashlib.sha256(json.dumps(stable,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()}
        if len(raw)>700000:
            compressed=gzip.compress(raw)
            if len(compressed)>850000:raise ValueError('PUBLIC_CACHE_TOO_LARGE')
            row['payloadGzip']=compressed
        else:row['payload']=payload
        self.db.collection('fcc_public_cache').document(key).set(row)
