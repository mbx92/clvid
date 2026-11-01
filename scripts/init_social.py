"""Initialize local token encryption without printing the key or replacing it."""
import base64
import secrets
from pathlib import Path

path=Path(__file__).resolve().parents[1]/'.env'
if not path.exists(): raise SystemExit('Buat .env terlebih dahulu.')
text=path.read_text(encoding='utf-8')
lines=text.splitlines()
key='SOCIAL_ENCRYPTION_KEY'
existing=next((line for line in lines if line.startswith(key+'=')),None)
if existing and existing.split('=',1)[1].strip():
    print('Kunci sosial sudah tersedia; tidak diubah.')
else:
    value=key+'='+base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    if existing is not None: lines[lines.index(existing)]=value
    else: lines.append(value)
    path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Kunci sosial dibuat di .env; simpan cadangan .env secara privat.')
