import gzip
import json
from datetime import datetime, timezone
from uuid import uuid4
from google.cloud import firestore
from .config import settings, MAX_LEAGUES_PER_USER

def now():
    return datetime.now(timezone.utc).isoformat()

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
        return removed

    def save_payload(self, uid, lid, payload, version):
        # Write an immutable revision, then publish its pointer atomically.
        revision = uuid4().hex
        root = self.league(uid, lid)
        packed = gzip.compress(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode())
        chunks = [packed[i:i+600_000] for i in range(0, len(packed), 600_000)]
        batch = self.db.batch()
        for i, chunk in enumerate(chunks):
            batch.set(root.collection('revisions').document(revision).collection('chunks').document(str(i)), {'data': chunk})
        batch.set(root.collection('revisions').document(revision), {'chunks': len(chunks), 'createdAt': now()})
        batch.commit()
        if not self.update_binding(uid,lid,version,{'revision': revision, 'lastSuccessAt': now(), 'status': 'ready', 'lastError': ''}):
            self.db.recursive_delete(root.collection('revisions').document(revision))
            return False
        # Retain recent generations so an in-flight reader can finish safely.
        current=(root.get().to_dict() or {}).get('revision')
        for old in root.collection('revisions').stream():
            created=(old.to_dict() or {}).get('createdAt','')
            try:age=(datetime.now(timezone.utc)-datetime.fromisoformat(created)).total_seconds()
            except (ValueError,TypeError):continue
            if old.id != current and age>86400:
                self.db.recursive_delete(old.reference)
        return True

    def read_payload(self, uid, lid, row):
        rev = row.get('revision')
        if not rev:
            return None
        ref = self.league(uid, lid).collection('revisions').document(rev)
        info = ref.get().to_dict() or {}
        try:
            packed = b''.join((ref.collection('chunks').document(str(i)).get().to_dict() or {})['data']
                              for i in range(int(info.get('chunks', 0))))
            return json.loads(gzip.decompress(packed))
        except (KeyError, OSError, ValueError):
            # A revision may be retired between pointer and chunk reads. Retry latest.
            current=self.get(uid,lid)
            if current and current.get('revision') and current['revision']!=rev:
                return self.read_payload(uid,lid,current)
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
        return self.db.collection('fcc_public_cache').document(key).get().to_dict()

    def save_public_cache(self,key,payload):
        import time
        self.db.collection('fcc_public_cache').document(key).set({'savedEpoch':time.time(),'payload':payload})
