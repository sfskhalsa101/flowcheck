"""Build the dependency-free GitHub Pages demo into docs/ (preserves guides)."""
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parent
target=ROOT/'docs'
target.mkdir(exist_ok=True)
html=(ROOT/'static/index.html').read_text()
html=html.replace('href="/styles.css"','href="./styles.css"').replace('src="/app.js"','src="./app.js"')
html=html.replace('<script src="./app.js"','<script src="./browser-demo.js" defer></script><script src="./app.js"')
html=html.replace('href="/"','href="./"')
html=html.replace('Synthetic data demo','Public browser demo')
html=html.replace('Last 100 snapshots · stored on this computer','Last 100 snapshots · saved in this browser only')
html=html.replace('Every result keeps its source records,<br>rule version, and audit history.','Records and history stay in this browser.<br>No uploads to a backend service.')
html=html.replace('All sample records are fictional. No measured savings are claimed.','Fictional samples · browser-only demo · <a href="https://github.com/sfskhalsa101/flowcheck">Python/SQL source ↗</a>')
html=html.replace('<section class="workbench"','<p class="hint">Try the preloaded sample, then load the corrected sample and compare again. No sign-in or installation. This public demo runs JavaScript locally; the repository contains the Python/SQLite implementation. Use one tab at a time.</p><section class="workbench"')
(target/'index.html').write_text(html)
for file in ('styles.css','app.js','browser-demo.js'):
    shutil.copy2(ROOT/'static'/file,target/file)
(target/'samples').mkdir(exist_ok=True)
for path in (ROOT/'samples').glob('*.csv'):
    shutil.copy2(path,target/'samples'/path.name)
(target/'.nojekyll').write_text('\n')
print('Built public demo in docs/')
