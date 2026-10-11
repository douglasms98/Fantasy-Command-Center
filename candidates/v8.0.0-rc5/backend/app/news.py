"""Cloud roster news. Only public article titles are sent for translation."""
import asyncio
import time
from datetime import timezone
import httpx
from .player_stats import name_key
from .translation import translate_titles
from .config import settings

class News:
    def __init__(self,store):self.store=store

    async def get(self,players):
        # Fetch and optionally translate the same general public feed for every
        # account. Private roster selection is applied locally after this work.
        if not players:return []
        key='espn-nfl-news-rc4'
        try:cached=self.store.public_cache(key)
        except Exception:cached=None
        raw=(cached or {}).get('payload') or {'articles':[]}
        async with httpx.AsyncClient(timeout=12,follow_redirects=False) as client:
            if not cached or time.time()-cached.get('savedEpoch',0)>=900:
                try:
                    async def public_feed(url,field):
                        response=await client.get(url,params={'limit':100});response.raise_for_status()
                        return response.json().get(field,[])
                    fetched=await asyncio.gather(
                        public_feed('https://site.api.espn.com/apis/site/v2/sports/football/nfl/news','articles'),
                        public_feed('https://site.api.espn.com/apis/fantasy/v2/games/ffl/news/players','feed'),return_exceptions=True)
                    articles=[a for rows in fetched if isinstance(rows,list) for a in rows]
                    if articles:raw={'articles':articles}
                    try:self.store.save_public_cache(key,raw)
                    except Exception:pass
                except Exception:pass
            try:public_names=(self.store.public_cache('nfl-public-names') or {}).get('payload',{}).get('names',[])
            except Exception:public_names=[]
            try:prior=self.store.public_cache('nfl-news-translated-rc4')
            except Exception:prior=None
            translations={a.get('headline'):a.get('titlePt') for a in (prior or {}).get('payload',{}).get('articles',[]) if a.get('titlePt')}
            articles=raw.get('articles',[])[:200]
            titles=[a.get('headline') for a in articles if a.get('headline') not in translations]
            if titles and settings().FCC_TRANSLATE_NEWS:
                translations.update(await translate_titles(client,titles,public_names))
            articles=[{**a,'titlePt':translations.get(a.get('headline')) or '',
                       'translationStatus':'translated' if translations.get(a.get('headline')) else 'pending'} for a in articles]
            if any(a.get('titlePt') for a in articles):
                try:self.store.save_public_cache('nfl-news-translated-rc4',{'articles':articles})
                except Exception:pass
        return espn_articles({'articles':articles},players)[:12]


def espn_articles(raw,players):
    from datetime import datetime,timedelta
    cutoff=datetime.now(timezone.utc)-timedelta(days=3)
    names={p.get('player') for p in players if p.get('player')}
    # An explicit empty espnId is a Sleeper player without an ESPN mapping.
    # Its Sleeper ID must never be mistaken for an unrelated ESPN athlete.
    by_id={str(p.get('espnId',p.get('playerId'))):p['player'] for p in players
           if p.get('player') and p.get('espnId',p.get('playerId'))}
    rows=[]
    for a in raw.get('articles',[]):
        title=a.get('headline') or '';text=name_key(title+' '+(a.get('description') or ''))
        matched={n for n in names if name_key(n) in text}
        if str(a.get('playerId')) in by_id:matched.add(by_id[str(a['playerId'])])
        for category in a.get('categories',[]):
            if category.get('type')=='athlete':
                pid=str(category.get('athleteId') or (category.get('athlete') or {}).get('id') or category.get('id'))
                if pid in by_id:matched.add(by_id[pid])
        if not matched:continue
        published=a.get('published') or a.get('lastModified') or ''
        try:date=datetime.fromisoformat(published.replace('Z','+00:00')).astimezone(timezone.utc)
        except (ValueError,TypeError):continue
        if date<cutoff:continue
        url=((a.get('links') or {}).get('web') or {}).get('href') or ''
        if not url.startswith('https://'):continue
        rows.append({'id':str(a.get('id','')),'title':title,'source':'ESPN','url':url,
                     'players':sorted(matched),'publishedAt':date.isoformat(),'language':'pt-BR' if a.get('titlePt') else 'en','titlePt':a.get('titlePt') or '', 'translationStatus':a.get('translationStatus') or 'pending'})
    return sorted(rows,key=lambda n:n['publishedAt'],reverse=True)
