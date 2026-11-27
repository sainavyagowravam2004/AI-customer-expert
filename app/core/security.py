import base64, hashlib, hmac, os
from cryptography.fernet import Fernet
from app.core.config import settings

def _fernet() -> Fernet:
    key = hashlib.sha256(settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))

def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()

def decrypt_secret(token: str | None) -> str:
    if not token:
        return ""
    return _fernet().decrypt(token.encode()).decode()

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return f"{salt.hex()}:{dk.hex()}"

def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split(":", 1)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 100_000)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False
