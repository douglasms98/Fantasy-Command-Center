"""Source/asset checks; Java parsing does not substitute for an Android build."""
from pathlib import Path
import ast
import xml.etree.ElementTree as ET
import javalang

root=Path(__file__).resolve().parents[1]
android=root/'app/src/main'
html=android/'assets/fcc/index.html'
assert html.read_bytes()==(root/'backend/static/index.html').read_bytes(),'Android and web HTML differ'
python_files=list((root/'backend/app').glob('*.py'))+list((root/'tools').glob('*.py'))
for path in python_files:ast.parse(path.read_text(),filename=str(path))
java_files=list((android/'java').rglob('*.java'))
for path in java_files:javalang.parse.parse(path.read_text())
xml_files=list(android.rglob('*.xml'))
for path in xml_files:ET.parse(path)
print(f'PASS: {len(python_files)} Python, {len(java_files)} Java and {len(xml_files)} XML files parse; Android/web assets match.')
print('Not run here: Gradle/Android compilation, device delivery, real Firebase/Firestore/provider access, Cloud deployment, visual render.')
