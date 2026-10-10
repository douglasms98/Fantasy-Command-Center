"""Keep the source fragment identical in the web and Android HTML."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
path=root/'backend/static/index.html'
text=path.read_text()
start='// BEGIN FCC GOOGLE AUTH\n'
end='// END FCC GOOGLE AUTH\n'
fragment=(root/'tools/google_ui.js').read_text()
if start in text:
    before,rest=text.split(start,1)
    _,after=rest.split(end,1)
    text=before+start+fragment+end+after
else:
    anchor='fccRestoreNativeCache=()=>false;'
    assert text.count(anchor)==1
    text=text.replace(anchor,start+fragment+end+'\n'+anchor)
path.write_text(text)
(root/'app/src/main/assets/fcc/index.html').write_text(text)
