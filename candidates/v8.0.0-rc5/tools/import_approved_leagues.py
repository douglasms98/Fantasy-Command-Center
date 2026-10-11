"""Import an explicit owner's league mapping; never copy a global account snapshot."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from firebase_admin import auth
from app.security import firebase_app
from app.providers import LeagueInput, Providers
from app.service import Service
from app.store import Store

async def run(args):
    owner=auth.get_user(args.uid,app=firebase_app())
    if owner.disabled or not owner.email_verified:raise ValueError('Confirm the owner account first')
    rows=json.loads(Path(args.input).read_text())
    if not isinstance(rows,list) or not rows:raise ValueError('Expected a nonempty list of LeagueInput objects')
    bindings=[LeagueInput.model_validate(row) for row in rows]
    repo=Store();provider=Providers();svc=Service(repo,provider)
    # Inspect every binding before the first write. No partial import on validation failure.
    for row in bindings:await provider.inspect(row)
    if not args.apply:
        print(f'Validated {len(bindings)} bindings. Dry run: no Cloud data changed.');return
    repo.profile(owner.uid,owner.email)
    for row in bindings:
        result,created=await svc.add(owner.uid,row)
        print(f'{result["platform"]}: {result["id"]} ({"created" if created else "already present"})')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uid',required=True,help='Verified FCC Firebase owner UID')
    parser.add_argument('--input',required=True,help='Local approved mapping JSON; do not commit it')
    parser.add_argument('--apply',action='store_true',help='Write inspected bindings to this UID only')
    args=parser.parse_args()
    try:asyncio.run(run(args))
    except Exception:raise SystemExit('Import failed. Check owner verification, mapping, provider access and IAM.') from None
