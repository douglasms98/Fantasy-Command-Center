"""Public NFL facts, shared across users; never uses another user's fantasy league."""
import asyncio
import json
import math
import time
import unicodedata

POSITIONS={1:'QB',2:'RB',3:'WR',4:'TE',5:'K',16:'DEF'}
NFL_TEAMS={1:'ATL',2:'BUF',3:'CHI',4:'CIN',5:'CLE',6:'DAL',7:'DEN',8:'DET',9:'GB',10:'TEN',11:'IND',12:'KC',13:'LV',14:'LAR',15:'MIA',16:'MIN',17:'NE',18:'NO',19:'NYG',20:'NYJ',21:'PHI',22:'ARI',23:'PIT',24:'LAC',25:'SF',26:'SEA',27:'TB',28:'WAS',29:'CAR',30:'JAX',33:'BAL',34:'HOU'}
BASE='https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons'

def number(value):
    if value is None or isinstance(value,bool):return None
    try:
        result=float(value)
        return result if math.isfinite(result) else None
    except (ValueError,TypeError):return None

def name_key(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(value or '')).lower() if c.isalnum())

def normalize_players(raw,season,week):
    entries=raw.get('players',[]) if isinstance(raw,dict) else raw if isinstance(raw,list) else []
    result={}
    for entry in entries:
        p=entry.get('player') or entry
        pos=POSITIONS.get(p.get('defaultPositionId'))
        if not pos or p.get('id') is None:continue
        history={};projection=None;actual=None
        for s in p.get('stats') or []:
            if s.get('seasonId')!=season or s.get('statSplitTypeId')!=1:continue
            w=int(s.get('scoringPeriodId') or 0)
            stats=s.get('stats')
            if not isinstance(stats,dict) or not stats:continue
            # Source and period must both match; a previous-week or season total
            # is never advertised as the current projection.
            if s.get('statSourceId')==1 and w==week:projection=stats
            if s.get('statSourceId')==0 and 0<w<week:history[str(w)]=stats
            if s.get('statSourceId')==0 and w==week:actual=stats
        result[str(p['id'])]={'id':str(p['id']),'name':p.get('fullName') or '',
          'pos':pos,'nfl':NFL_TEAMS.get(p.get('proTeamId'),''),
          'history':history,'projection':projection,'actual':actual}
    return result

class PublicPlayerStats:
    def __init__(self,store=None):self.store=store;self.cache={};self.lock=asyncio.Lock()

    async def get(self,c,season,week):
        key=f'nfl-player-stats-rc4-{season}-{week}'
        cached=self.cache.get(key)
        if cached and time.time()-cached['savedEpoch']<900:return cached['payload']
        async with self.lock:
            cached=self.cache.get(key)
            if cached and time.time()-cached['savedEpoch']<900:return cached['payload']
            if self.store:
                try:cached=self.store.public_cache(key)
                except Exception:cached=None
                if cached and time.time()-cached.get('savedEpoch',0)<900:
                    self.cache[key]=cached;return cached['payload']
            common={'filterActive':{'value':True},'filterStatsForSplitTypeIds':{'value':[1]}}
            filters=[{**common,'filterStatsForSourceIds':{'value':[0]},'filterStatsForTopScoringPeriodIds':{'value':week,'additionalValue':[f'00{season}']}},
                     {**common,'filterStatsForSourceIds':{'value':[1]},'filterStatsForExternalIds':{'value':[f'{season}{week}']}}]
            async def fetch(f):
                try:
                    r=await c.get(f'{BASE}/{season}/players',params=[('view','players_wl'),('view','kona_player_info'),('scoringPeriodId',week)],headers={'X-Fantasy-Filter':json.dumps(f)})
                    r.raise_for_status();return normalize_players(r.json(),season,week)
                except Exception:return {}
            history,projections=await asyncio.gather(*(fetch(f) for f in filters))
            result=history
            for pid,p in projections.items():
                old=result.get(pid)
                if old:p['history']={**old['history'],**p['history']};p['actual']=p['actual'] if p['actual'] is not None else old['actual']
                result[pid]=p
            if not result:return cached['payload'] if cached else {}
            payload={'season':season,'week':week,'players':result,'projectionAvailable':any(p['projection'] is not None for p in result.values())}
            self.cache={key:{'savedEpoch':time.time(),'payload':payload}}
            if self.store:
                try:
                    self.store.save_public_cache(key,payload)
                    self.store.save_public_cache('nfl-public-names',{'names':sorted({p['name'] for p in result.values() if p['name']})})
                except Exception:pass
            return payload

OFFENSE={'pass_att':'0','pass_cmp':'1','pass_inc':'2','pass_yd':'3','pass_td':'4',
 'pass_2pt':'19','pass_int':'20','rush_att':'23','rush_yd':'24','rush_td':'25',
 'rush_2pt':'26','rec':'53','rec_yd':'42','rec_td':'43','rec_2pt':'44',
 'pass_sack':'64','fum':'68','fum_lost':'72','fum_rec_td':'63','kr_yd':'114','pr_yd':'115',
 'pass_fd':'211','rush_fd':'212','rec_fd':'213','st_td':('101','102','93')}
BONUSES={'bonus_pass_yd_300':('17','18'),'bonus_pass_yd_400':('18',),
 'bonus_rush_yd_100':('37','38'),'bonus_rush_yd_200':('38',),
 'bonus_rec_yd_100':('56','57'),'bonus_rec_yd_200':('57',)}
KICKING={'fgm':'83','fgmiss':'85','fgm_40_49':'77','fgm_50p':'74','fgm_50_59':'198',
 'fgm_60p':'201','fgmiss_40_49':'79','fgmiss_50p':'76','fgmiss_50_59':'200',
 'fgmiss_60p':'203','xpm':'86','xpmiss':'88','fgm_yds':'214','fgmiss_yds':'215'}
DEFENSE={'sack':'99','int':'95','fum_rec':'96','ff':'106','blk_kick':'97','safe':'98',
 'def_td':'94','def_st_td':('101','102','93'),'def_2pt':'205','pts_allow':'187',
 'yds_allow':'127','tkl_solo':'108','tkl_ast':'107','tkl':'109','tkl_loss':'112','def_pass_def':'113'}

def sleeper_score(stats,settings,pos):
    """Rescore provider facts. Unsupported nonzero rules yield null, never a guess."""
    if not isinstance(stats,dict) or not stats or not settings:return None
    get=lambda key:number(stats.get(key)) or 0.0
    total=0.0
    if pos in ('QB','RB','WR','TE'):
        # Defensive fumble recoveries are a different setting from an offensive
        # fumble touchdown. Do not apply defensive rules to offensive players.
        relevant=lambda k:(k.startswith(('pass_','rush_','rec','bonus_','kr_','pr_')) or k in ('fum','fum_lost','fum_rec_td','st_td'))
        mapping=OFFENSE
    elif pos=='K':relevant=lambda k:k.startswith(('fg','xp'));mapping=KICKING
    elif pos=='DEF':
        relevant=lambda k:not k.startswith(('pass_','rush_','rec','bonus_','fum_lost','fg','xp','idp_','kr_','pr_'))
        mapping=DEFENSE
    else:return None
    for key,raw in settings.items():
        coefficient=number(raw)
        if not coefficient or not relevant(key):continue
        if key in mapping:
            ids=mapping[key] if isinstance(mapping[key],tuple) else (mapping[key],)
            total+=sum(get(k) for k in ids)*coefficient
        elif key in BONUSES and pos in ('QB','RB','WR','TE'):total+=sum(get(k) for k in BONUSES[key])*coefficient
        elif key in ('bonus_rec_te','bonus_rec_wr','bonus_rec_rb'):
            if pos==key.rsplit('_',1)[1].upper():total+=get('53')*coefficient
        elif key in ('pass_int_td','pass_cmp_40p') and get('20' if key=='pass_int_td' else '1')==0:
            # Zero interceptions/completions also means zero in their subsets.
            # Positive totals cannot reveal the subset; that stays unsupported.
            continue
        elif pos=='K' and key in ('fgm_0_19','fgm_20_29','fgm_30_39','fgmiss_0_19','fgmiss_20_29','fgmiss_30_39'):
            prefix=key.split('_',1)[0]
            rates=[number(settings.get(prefix+'_'+r)) or 0 for r in ('0_19','20_29','30_39')]
            if len(set(rates))!=1:return None
            if key.endswith('0_19'):total+=get('80' if prefix=='fgm' else '82')*coefficient
        elif pos=='DEF' and key.startswith('pts_allow_'):
            # NFL/ESPN D/ST ranges differ at 18/21 points. Exact actual values are
            # usable; projections cannot be rebucketed with guessed probabilities.
            allowed=number(stats.get('187'))
            if allowed is None:return None
            bounds={'0':(0,0),'1_6':(1,6),'7_13':(7,13),'14_20':(14,20),'21_27':(21,27),'28_34':(28,34),'35p':(35,1e9)}
            interval=bounds.get(key[len('pts_allow_'):])
            if interval is None:return None
            if not allowed.is_integer():return None
            if interval[0]<=allowed<=interval[1]:total+=coefficient
        else:return None
    return round(total,4)

def espn_score(stats,items):
    if not stats or not items:return None
    total=0.0
    for item in items:
        value=number(stats.get(str(item.get('statId'))))
        coefficient=number(item.get('points'))
        if value is not None and coefficient is not None:total+=value*coefficient
    return round(total,4)
