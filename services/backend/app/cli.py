import argparse
import getpass

from argon2 import PasswordHasher
from sqlalchemy import select, update

from app.db import session_scope
from app.domain.models import Session, User, utcnow


def main():
    parser = argparse.ArgumentParser(description="Kelola akun Clipper secara lokal; tidak ada registrasi publik.")
    parser.add_argument("command", choices=["create-user", "reset-password", "download-model"])
    parser.add_argument("--email", help="Email akun. Password selalu dibaca interaktif, tidak melalui argumen.")
    args = parser.parse_args()
    if args.command == "download-model":
        from faster_whisper import WhisperModel
        from app.config import get_settings
        config = get_settings()
        WhisperModel(config.whisper_model, device=config.whisper_device, compute_type=config.whisper_compute_type, download_root=config.whisper_download_root)
        print("Model transkripsi tersedia di cache.")
        return
    email = (args.email or input("Email akun: ")).strip().lower()
    if not email or len(email) > 254 or "@" not in email:
        parser.error("Masukkan email akun yang valid.")
    password = getpass.getpass("Kata sandi (minimal 12 karakter): ")
    if len(password) < 12 or len(password) > 1024:
        parser.error("Kata sandi harus 12–1024 karakter.")
    if password != getpass.getpass("Ulangi kata sandi: "):
        parser.error("Kata sandi tidak sama.")
    hashed = PasswordHasher().hash(password)
    with session_scope() as db:
        user = db.scalar(select(User).where(User.email == email))
        if args.command == "create-user":
            if user:
                parser.error("Akun sudah ada. Gunakan reset-password.")
            db.add(User(email=email, password_hash=hashed))
        else:
            if not user:
                parser.error("Akun tidak ditemukan.")
            user.password_hash = hashed
            db.execute(update(Session).where(Session.user_id == user.id).values(revoked_at=utcnow()))
    print("Akun berhasil dibuat." if args.command == "create-user" else "Kata sandi diperbarui; semua sesi lama dicabut.")


if __name__ == "__main__":
    main()
