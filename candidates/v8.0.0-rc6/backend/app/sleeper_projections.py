"""Shared public weekly Sleeper projections; no fantasy roster in requests."""
import asyncio
import time
from .player_stats import number

URL='https://api.sleeper.app/projections/nfl'
POSITIONS={'QB','RB','WR','TE','K','DEF'}
OFFENSE_PREFIXES=('pass_','rush_','rec','bonus_','kr_','pr_')
OFFENSE_OTHER={'fum','fum_lost','fum_rec_td','st_td'}
# The public projection feed omits zero-valued ordinary statistics. An ADP-only
# row is not a projection. Special rules outside this vocabulary require a
# supplied statistic; they are never inferred from yardage or another league.
ORDINARY={'pass_att','pass_cmp','pass_inc','pass_yd','pass_td','pass_2pt','pass_int','pass_sack',
 'rush_att','rush_yd','rush_td','rush_2pt','rec','rec_yd','rec_td','rec_2pt','fum','fum_lost',
 'fgm','fgm_0_19','fgm_20_29','fgm_30_39','fgm_40_49','fgm_50p',
 'fgmiss_0_19','fgmiss_20_29','fgmiss_30_39','fgmiss_40_49','fgmiss_50p','xpm','xpmiss',
 'sack','int','fum_rec','ff','blk_kick','safe','def_td','st_td'}

def relevant(key,pos):
    if key in ('bonus_rec_te','bonus_rec_wr','bonus_rec_rb'):
        return pos==key.rsplit('_',1)[1].upper()
    if key=='bonus_rush_td_qb':return pos=='QB'
    if pos in ('QB','RB','WR','TE'):return key.startswith(OFFENSE_PREFIXES) or key in OFFENSE_OTHER
    if pos=='K':return key.startswith(('fg','xp'))
    return not key.startswith(('pass_','rush_','rec','bonus_','fum_lost','fg','xp','idp_','kr_','pr_'))

def projection_details(stats,rules,pos):
    if not isinstance(stats,dict) or not rules or pos not in POSITIONS:return {'value':None,'missing':[]}
    if not any(k in ORDINARY or k.startswith(('pts_allow_','yds_allow_')) for k in stats):return {'value':None,'missing':[]}
    total=0.0;missing=[]
    for key,raw in rules.items():
        rate=number(raw)
        if not rate or not relevant(key,pos):continue
        value=number(stats.get(key))
        if value is None and key in ('bonus_rec_te','bonus_rec_wr','bonus_rec_rb'):value=number(stats.get('rec'))
        if value is None and key=='fgmiss' and 'fga' in stats and 'fgm' in stats:
            attempts=number(stats['fga']);made=number(stats['fgm'])
            if attempts is not None and made is not None:value=max(0,attempts-made)
        if value is None and key=='def_st_td' and all(k in stats for k in ('def_kr_td','def_pr_td')):
            values=[number(stats[k]) for k in ('def_kr_td','def_pr_td')]
            if all(v is not None for v in values):value=sum(values)
        if value is None and key in ORDINARY and key not in stats:value=0.0
        if value is None:missing.append(key);continue
        total+=rate*value
    return {'value':round(total,4),'missing':missing}

def score_projection(stats,rules,pos):
    details=projection_details(stats,rules,pos)
    return None if details['missing'] else details['value']

def normalize(raw,season,week):
    players={}
    for row in raw if isinstance(raw,list) else []:
        try:matches=int(row.get('season',0))==season and int(row.get('week',0))==week
        except (ValueError,TypeError):continue
        if not matches or row.get('season_type')!='regular':continue
        player=row.get('player') or {};pos=player.get('position');pid=str(row.get('player_id') or '')
        stats=row.get('stats') or {}
        if not pid or pos not in POSITIONS or not isinstance(stats,dict):continue
        if not any(k in ORDINARY or k.startswith(('pts_allow_','yds_allow_')) for k in stats):continue
        # Prefer the current Rotowire publication; never combine two forecasts.
        rank=(row.get('company')=='rotowire',number(row.get('last_modified')) or 0)
        if pid in players and rank<=players[pid]['_rank']:continue
        players[pid]={'stats':{k:v for k,v in stats.items() if number(v) is not None and not k.startswith(('adp_','pos_adp_'))},
                      'pos':pos,'nfl':row.get('team') or player.get('team') or '',
                      'source':'Sleeper • '+str(row.get('company') or 'projeção publicada'),'_rank':rank}
    for value in players.values():value.pop('_rank')
    return {'season':season,'week':week,'players':players}

class SleeperProjections:
    def __init__(self,store=None):self.store=store;self.cache={};self.lock=asyncio.Lock()

    async def get(self,client,season,week):
        key=f'sleeper-projections-rc5-{season}-{week}'
        async with self.lock:
            cached=self.cache.get(key)
            if not cached and self.store:
                try:cached=self.store.public_cache(key)
                except Exception:pass
            if cached and time.time()-cached.get('savedEpoch',0)<900:
                self.cache[key]=cached;return cached['payload']
            try:
                response=await client.get(f'{URL}/{season}/{week}',params={'season_type':'regular'})
                response.raise_for_status();payload=normalize(response.json(),season,week)
                if not payload['players']:return cached['payload'] if cached else {}
            except Exception:return cached['payload'] if cached else {}
            self.cache={key:{'savedEpoch':time.time(),'payload':payload}}
            if self.store:
                try:self.store.save_public_cache(key,payload)
                except Exception:pass
            return payload
