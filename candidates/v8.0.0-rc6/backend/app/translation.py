"""Optional Cloud Translation of public NFL headlines using runtime credentials."""
import asyncio
import html
import re
import threading
import google.auth
from google.auth.transport.requests import Request
from .config import settings

_credentials=None
_lock=threading.Lock()

def cloud_token():
    global _credentials
    with _lock:
        if _credentials is None:
            _credentials,_=google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
        if not _credentials.valid:_credentials.refresh(Request())
        return _credentials.token

def protect_title(title,names):
    protected={};text=title
    for term in sorted(set(names+['IR','NFL','PPR','QB','RB','WR','TE','FAAB']),key=len,reverse=True):
        pattern=r'(?<!\w)'+re.escape(term)+r'(?!\w)'
        if not re.search(pattern,text,re.I):continue
        token=f'FCCNAME{len(protected)}FCC';protected[token]=term
        text=re.sub(pattern,token,text,flags=re.I)
    return text,protected

async def translate_titles(client,titles,names):
    config=settings()
    if not config.FCC_TRANSLATE_NEWS or not config.FCC_GCP_PROJECT:return {}
    jobs=[(title,*protect_title(title,names)) for title in dict.fromkeys(titles) if title and len(title)<=500]
    if not jobs:return {}
    try:token=await asyncio.to_thread(cloud_token)
    except Exception:return {}
    groups=[];current=[];length=0
    for job in jobs:
        if length+len(job[1])>20000 or len(current)>=100:groups.append(current);current=[];length=0
        current.append(job);length+=len(job[1])
    if current:groups.append(current)
    result={}
    for group in groups:
        try:
            response=await client.post(f'https://translate.googleapis.com/v3/projects/{config.FCC_GCP_PROJECT}/locations/global:translateText',
                headers={'Authorization':'Bearer '+token},json={'contents':[j[1] for j in group],'mimeType':'text/plain','sourceLanguageCode':'en','targetLanguageCode':'pt'})
            response.raise_for_status();translations=response.json()['translations']
            if len(translations)!=len(group):continue
            for (title,_,protected),translated in zip(group,translations):
                pt=html.unescape(translated['translatedText'])
                if any(marker not in pt for marker in protected):continue
                for marker,term in protected.items():pt=pt.replace(marker,term)
                if pt:result[title]=pt
        except Exception:continue
    return result

async def translate_title(client,title,names):
    return (await translate_titles(client,[title],names)).get(title)
