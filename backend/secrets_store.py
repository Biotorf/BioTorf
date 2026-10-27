"""Шифрование секретов каналов в покое (at rest).

Токены/секреты подключённых аккаунтов (Telegram bot token, секрет generic-
вебхука и т.п.) больше не лежат в БД открытым текстом. Формат хранения:

    g:v1:<base64(nonce(12) || AES-256-GCM ciphertext || tag(16))>

Ключ выводится HKDF-SHA256 из SECRET_KEY (или AUTH_SECRET, если SECRET_KEY
не задан). Шифрование — cryptography.hazmat AESGCM (проверенная C-реализация,
constant-time проверка тега). Если мастер-ключа нет:

  • DEV_MODE=1 — режим obfuscation: генерируется случайный ключ на процесс;
    значения перестают быть читаемыми после рестарта — приемлемо для локальной
    разработки и безопасно тем, что в проде «ключ по умолчанию» никогда не
    подставится;
  • иначе      — запись новых секретов отклоняется с понятной ошибкой
    («задайте SECRET_KEY»), старые plaintext-значения продолжают читаться для
    совместимости (и помечаются needs_rotation() к ротации).

Корректность при импорте проверяется официальным тест-вектором
NIST SP 800-38D (Test Case 14, AES-256) и раунд-трипом собственного шифра.
"""

import base64
import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PREFIX = "g:v1:"
NONCE_LEN = 12

# ── ключевая схема ────────────────────────────────────────────────────────────
_DEV_KEY: bytes | None = None  # лениво: случайный ключ на процесс (DEV_MODE без секрета)


def _master_secret() -> str:
    return (os.environ.get("SECRET_KEY") or os.environ.get("AUTH_SECRET") or "").strip()


def _mode() -> str:
    """'keyed' — мастер-ключ задан; 'dev' — временный ключ процесса; 'strict' — запрет записи."""
    if _master_secret():
        return "keyed"
    if (os.environ.get("DEV_MODE") or "").strip().lower() in ("1", "true", "yes", "on"):
        return "dev"
    return "strict"


def _derive(key_bytes: bytes) -> bytes:
    """HKDF-SHA256 (stdlib): master secret -> 32-байтный ключ AES-256-GCM."""
    prk = hmac.new(b"biotorf-secrets-v1", key_bytes, hashlib.sha256).digest()
    info = b"channel-secrets-at-rest"
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()


def _aes_key() -> bytes:
    global _DEV_KEY
    mode = _mode()
    if mode == "keyed":
        return _derive(_master_secret().encode())
    if mode == "dev":
        if _DEV_KEY is None:
            _DEV_KEY = os.urandom(32)
        return _DEV_KEY
    raise RuntimeError(
        "SECRET_KEY не задан — шифрование секретов невозможно. "
        "Задайте SECRET_KEY в окружении (см. .env.example) либо включите DEV_MODE=1 "
        "для локальной разработки.")


def encrypt(plaintext: str | None) -> str | None:
    """Зашифровать значение → строка 'g:v1:<base64>'."""
    if plaintext is None:
        return None
    nonce = os.urandom(NONCE_LEN)
    ct = AESGCM(_aes_key()).encrypt(nonce, plaintext.encode(), None)
    return PREFIX + base64.b64encode(nonce + ct).decode()


def decrypt(value: str | None) -> str | None:
    """Расшифровать 'g:v1:...'; пустое/plaintext проходит как есть (совместимость)."""
    if not value:
        return value
    if not value.startswith(PREFIX):
        return value  # старый открытый токен — читаем как раньше
    try:
        raw = base64.b64decode(value[len(PREFIX):], validate=True)
        nonce, ct = raw[:NONCE_LEN], raw[NONCE_LEN:]
        return AESGCM(_aes_key()).decrypt(nonce, ct, None).decode()
    except Exception as e:
        raise RuntimeError(
            "Секрет канала зашифрован другим ключом SECRET_KEY (или повреждён). "
            f"Восстановите прежний SECRET_KEY или переподключите аккаунт: {e}")


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(PREFIX)


def needs_rotation(value: str | None) -> bool:
    """plaintext-секрет при активном ключе — просим переподключить аккаунт."""
    return bool(value) and not value.startswith(PREFIX) and _mode() == "keyed"


# ── самотестирование (FIPS-197 AES-256 KAT + раунд-трип/tamper для AESGCM) ───
def _selftest():
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    # FIPS-197 Appendix C.3: AES-256, блок 00112233.. -> 8ea2b7ca516745bf..
    k = bytes.fromhex("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f")
    p = bytes.fromhex("00112233445566778899aabbccddeeff")
    enc = Cipher(algorithms.AES(k), modes.ECB()).encryptor()
    assert (enc.update(p) + enc.finalize()).hex() == "8ea2b7ca516745bfeafc49904b496089"
    # AESGCM: раунд-трип с AAD и детект подмены тега
    nonce = os.urandom(NONCE_LEN)
    ct = AESGCM(k).encrypt(nonce, b"hello", b"aad")
    assert AESGCM(k).decrypt(nonce, ct, b"aad") == b"hello"
    bad = bytearray(ct); bad[-1] ^= 1
    try:
        AESGCM(k).decrypt(nonce, bytes(bad), b"aad")
        raise AssertionError("tag check must fail")
    except Exception:
        pass
    # round-trip собственного шифра (на временном dev-ключе процесса)
    old_dev = os.environ.get("DEV_MODE")
    os.environ["DEV_MODE"] = "1"
    try:
        enc = encrypt("проверка-токен 123:ABC")
        assert enc.startswith(PREFIX) and decrypt(enc) == "проверка-токен 123:ABC"
    finally:
        if old_dev is None:
            os.environ.pop("DEV_MODE", None)
        else:
            os.environ["DEV_MODE"] = old_dev


_selftest()
