"""Admin-only approval of an existing per-user Secret Manager connection."""
import argparse
import asyncio
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from firebase_admin import auth
from app.security import firebase_app
from app.providers import Providers
from app.service import Service
from app.store import Store

async def run(args):
    owner=auth.get_user(args.uid,app=firebase_app())
    if owner.disabled or not owner.email_verified:raise ValueError('Owner not verified')
    repo=Store();provider=Providers();row=Service(repo,provider).owned(args.uid,args.league)
    if row['platform']!='ESPN':raise ValueError('Not an ESPN binding')
    expected=f'fcc-espn-{args.uid}-{args.league}'
    if args.secret!=expected:raise ValueError('Secret must belong to this owner and binding')
    credentials=repo.credentials(args.uid,args.league,args.secret)
    payload=await provider.fetch(row,credentials)
    if not payload.get('loaded'):raise ValueError('Provider data not verified')
    if not args.apply:
        print('Provider connection validated. Dry run: no binding changed.');return
    if not repo.update_binding(args.uid,args.league,row.get('bindingVersion'),{'credentialSecret':args.secret}):
        raise ValueError('Binding changed')
    if not repo.save_payload(args.uid,args.league,payload,row.get('bindingVersion')):raise ValueError('Binding changed')
    print('Private ESPN connection approved for this FCC account and league.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uid',required=True)
    parser.add_argument('--league',required=True,help='FCC binding ID, not external ESPN ID')
    parser.add_argument('--secret',required=True,help='Secret name only; never provide cookie values here')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    try:asyncio.run(run(args))
    except Exception:raise SystemExit('Connection failed. Check account consent, secret scope, provider access and IAM.') from None
