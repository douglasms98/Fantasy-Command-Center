"""Shared public NFL calendar; no fantasy account credentials or default fixtures."""
import time
import asyncio
from datetime import datetime, timezone
import httpx
from fastapi import HTTPException
from .store import now

BASE='https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard'

def team_code(value):
    code=str(value or '').strip().upper()
    return {'WSH':'WAS','JAC':'JAX'}.get(code,code)

def normalize(raw,week):
    games=[]
    for event in raw.get('events') or []:
        competition=next(iter(event.get('competitions') or []),{})
        competitors=competition.get('competitors') or []
        teams={c.get('homeAway'):team_code((c.get('team') or {}).get('abbreviation')) for c in competitors}
        if not teams.get('home') or not teams.get('away'):continue
        status=event.get('status') or {};kind=status.get('type') or {}
        venue=competition.get('venue') or {};country=(venue.get('address') or {}).get('country') or ''
        games.append({'id':str(event.get('id') or ''),'week':week,'home':teams['home'],'away':teams['away'],
                      'startTime':event.get('date') or competition.get('date') or '',
                      'state':kind.get('state') or '', 'status':kind.get('detail') or kind.get('shortDetail') or '',
                      'completed':kind.get('completed') is True,'live':kind.get('state')=='in',
                      'period':status.get('period'), 'clock':status.get('displayClock') or '',
                      'venue':venue.get('fullName') or '', 'country':country,
                      'neutralSite':competition.get('neutralSite') is True,
                      'international':bool(country and country.lower() not in ('usa','us','united states','estados unidos'))})
    complete=bool(games and len(games)==len(raw.get('events') or []) and (raw.get('week') or {}).get('number')==week)
    return {'week':week,'source':'ESPN NFL scoreboard','games':games,'complete':complete}

class Calendar:
    def __init__(self,store):self.store=store

    @staticmethod
    def key(season,week):return f'nfl-{season}-{week}'

    async def get(self,season,week):
        if not 1<=week<=18:return {'ok':True,'season':season,'weeks':[],'generatedAt':now()}
        key=self.key(season,week);cached=self.store.public_cache(key)
        if cached and time.time()-cached.get('savedEpoch',0)<300:return cached['payload']
        async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
            async def fetch(w):
                try:
                    response=await client.get(BASE,params={'dates':season,'seasontype':2,'week':w})
                    response.raise_for_status();raw=response.json()
                    confirmed_year=(raw.get('season') or {}).get('year')
                    confirmed_week=(raw.get('week') or {}).get('number')
                    if confirmed_year and int(confirmed_year)!=season:return None
                    if confirmed_week and int(confirmed_week)!=w:return None
                    return normalize(raw,w)
                except (httpx.HTTPError,ValueError,TypeError):return None
            results=await asyncio.gather(*(fetch(w) for w in range(max(1,week-1),min(18,week+3)+1)))
        weeks=[w for w in results if w is not None]
        if not weeks:
            if cached:return {**cached['payload'],'stale':True}
            raise HTTPException(502,'NFL_CALENDAR_UNAVAILABLE')
        payload={'ok':True,'season':season,'requestedWeek':week,'weeks':weeks,'generatedAt':now()}
        self.store.save_public_cache(key,payload)
        return payload
