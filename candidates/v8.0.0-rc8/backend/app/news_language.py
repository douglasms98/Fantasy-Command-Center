"""Shared deterministic NFL headline rules; no external model or paid API."""
import json
import re
from functools import lru_cache
from pathlib import Path

RULES=json.loads((Path(__file__).resolve().parent.parent/'static/news_language.json').read_text())
PATTERNS=[(re.compile(r['pattern'],re.I),r['template']) for r in RULES['patterns']]

def contextual_title(title):
    for pattern,template in PATTERNS:
        match=pattern.fullmatch(str(title or '').strip())
        if not match:continue
        def substitute(token):
            kind,index=token.groups();value=match.group(int(index)) or ''
            table=RULES.get('body' if kind=='b' else 'days',{})
            return next((v for k,v in table.items() if k.lower()==value.lower()),value) if kind else value
        return re.sub(r'\{([bd]?)(\d+)\}',substitute,template)
    return ''

@lru_cache(maxsize=4)
def name_pattern(names):
    terms=set(RULES['protectedTerms'])
    for name in names:
        terms.add(name)
        words=[w for w in name.split() if w.rstrip('.') not in ('Jr','Sr','II','III','IV')]
        if words and len(words[-1])>=4:terms.add(words[-1])
    alternatives='|'.join(re.escape(term) for term in sorted(terms,key=lambda s:(-len(s),s)) if term)
    return re.compile(r'(?<!\w)(?:'+alternatives+r')(?!\w)',re.I)

def protected_names(title,names):
    found={m.group() for m in name_pattern(tuple(names)).finditer(title)}
    return sorted(found,key=lambda s:(-len(s),s))

def translation_input(text):
    for phrase,value in RULES['inputPhrases'].items():
        text=re.sub(r'(?<!\w)'+re.escape(phrase)+r'(?!\w)',value,text,flags=re.I)
    return text
