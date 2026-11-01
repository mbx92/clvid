"""Create local configuration without printing or overwriting secrets."""
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
destination = root / ".env"
if destination.exists():
    raise SystemExit(".env sudah ada; tidak diubah.")
password = secrets.token_hex(32)
template = (root / ".env.example").read_text(encoding="utf-8")
with destination.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(template.replace("CHANGE_ME_GENERATE_LOCALLY", password))
try:
    destination.chmod(0o600)
except OSError:
    pass
print(".env dibuat. Isi DEEPSEEK_API_KEY secara lokal jika rekomendasi AI diperlukan.")
