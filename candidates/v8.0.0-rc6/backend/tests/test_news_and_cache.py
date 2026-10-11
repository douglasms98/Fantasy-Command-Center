"""TEST_ONLY fixtures; no public article text or credentials are embedded."""
import asyncio
from datetime import datetime,timezone
from types import SimpleNamespace
import httpx
from app.translation import translate_title
from app.news import espn_articles,News
from app.store import Store

def test_cloud_translation_keeps_player_names_and_ir(monkeypatch):
    monkeypatch.setattr('app.translation.settings',lambda:SimpleNamespace(FCC_TRANSLATE_NEWS=True,FCC_GCP_PROJECT='test-only'))
    monkeypatch.setattr('app.translation.cloud_token',lambda:'TEST_ONLY_TOKEN')
    requests=[]
    def response(request):
        requests.append(request)
        return httpx.Response(200,json={'translations':[{'translatedText':'FCCNAME0FCC permanece na FCCNAME1FCC'}]})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
            return await translate_title(client,'TEST_ONLY_PLAYER remains on IR',['TEST_ONLY_PLAYER'])
    assert asyncio.run(run())=='TEST_ONLY_PLAYER permanece na IR'
    assert requests[0].url.path.endswith('/locations/global:translateText')
    assert 'apiKey' not in requests[0].content.decode() and 'TEST_ONLY_TOKEN' not in requests[0].content.decode()

def test_lost_protected_name_rejects_translation(monkeypatch):
    monkeypatch.setattr('app.translation.settings',lambda:SimpleNamespace(FCC_TRANSLATE_NEWS=True,FCC_GCP_PROJECT='test-only'))
    monkeypatch.setattr('app.translation.cloud_token',lambda:'TEST_ONLY_TOKEN')
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'translations':[{'translatedText':'Nome alterado'}]}))) as c:
            return await translate_title(c,'TEST_ONLY_PLAYER remains on IR',['TEST_ONLY_PLAYER'])
    assert asyncio.run(run()) is None

def test_news_fallback_matches_only_account_players_by_id_or_name():
    at=datetime.now(timezone.utc).isoformat()
    raw={'articles':[{'id':1,'headline':'TEST_ONLY_PLAYER report','published':at,'links':{'web':{'href':'https://example.invalid/a'}}},
      {'id':2,'headline':'TEST_ONLY_OTHER report','published':at,'links':{'web':{'href':'https://example.invalid/b'}}},
      {'id':3,'headline':'TEST_ONLY report','published':at,'categories':[{'type':'athlete','athleteId':99}],'links':{'web':{'href':'https://example.invalid/c'}}}]}
    news=espn_articles(raw,[{'player':'TEST_ONLY_PLAYER','espnId':'99'}])
    assert {n['id'] for n in news}=={'1','3'}
    assert all(n['players']==['TEST_ONLY_PLAYER'] for n in news)

def test_large_public_cache_is_compressed_and_readable_without_firestore():
    rows={}
    class Ref:
        def set(self,row):rows.update(row)
        def get(self):return SimpleNamespace(to_dict=lambda:dict(rows))
    cache=Store.__new__(Store);cache.db=SimpleNamespace(collection=lambda n:SimpleNamespace(document=lambda k:Ref()))
    payload={'publicFacts':'TEST_ONLY_'*90000}
    cache.save_public_cache('TEST_ONLY',payload)
    assert 'payloadGzip' in rows and 'payload' not in rows
    assert len(rows['payloadGzip'])<850000
    assert cache.public_cache('TEST_ONLY')['payload']==payload

def test_unmapped_sleeper_id_is_not_an_espn_athlete_id():
    at=datetime.now(timezone.utc).isoformat()
    raw={'articles':[{'id':1,'headline':'TEST_ONLY_OTHER report','published':at,
        'categories':[{'type':'athlete','athleteId':99}],
        'links':{'web':{'href':'https://example.invalid/a'}}}]}
    assert espn_articles(raw,[{'player':'TEST_ONLY_SLEEPER','playerId':'99','espnId':''}])==[]
    assert espn_articles(raw,[{'player':'TEST_ONLY_ESPN','playerId':'99'}])[0]['players']==['TEST_ONLY_ESPN']

def test_public_news_request_never_contains_roster_selection(monkeypatch):
    import time
    rows={};requests=[];at=datetime.now(timezone.utc).isoformat()
    class Cache:
        def public_cache(self,key):return rows.get(key)
        def save_public_cache(self,key,payload):rows[key]={'savedEpoch':time.time(),'payload':payload}
    original=httpx.AsyncClient
    def response(request):
        requests.append(request)
        return httpx.Response(200,json={'articles':[{'id':i,'headline':name+' report','published':at,'links':{'web':{'href':f'https://example.invalid/{i}'}}} for i,name in enumerate(('TEST_ONLY_A','TEST_ONLY_B'))]})
    monkeypatch.setattr('app.news.httpx.AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(response),**kwargs))
    monkeypatch.setattr('app.news.settings',lambda:SimpleNamespace(FCC_TRANSLATE_NEWS=False))
    async def run():
        service=News(Cache())
        a=await service.get([{'player':'TEST_ONLY_A','playerId':'1'}])
        b=await service.get([{'player':'TEST_ONLY_B','playerId':'2'}])
        return a,b
    a,b=asyncio.run(run())
    assert a[0]['players']==['TEST_ONLY_A'] and b[0]['players']==['TEST_ONLY_B']
    assert len(requests)==2
    assert all(dict(r.url.params)=={'limit':'100'} for r in requests)
    assert all('TEST_ONLY_A' not in str(r.url) and 'TEST_ONLY_B' not in str(r.url) for r in requests)
