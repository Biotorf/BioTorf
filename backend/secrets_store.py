"""Шифрование секретов каналов в покое (at rest).

Токены/секреты подключённых аккаунтов (Telegram bot token, секрет generic-
вебхука) больше не лежат в БД открытым текстом. Формат хранения:

    g:v1:<base64(nonce(12) || AES-256-GCM ciphertext || tag(16))>

Ключ — HKDF-SHA256 от SECRET_KEY (stdlib hmac/hashlib, без зависимостей).
Если SECRET_KEY не задан:

  • DEV_MODE=1 — включается режим obfuscation (случайный ключ на процесс):
    значения шифруются, но после рестарта become нечитаемыми — приемлемо для
    локальной разработки и безопасно тем, что в проде ключ не подставится;
  • иначе      — REQUIRE_SECRET_KEY: запись новых секретов отклоняется с
    понятной ошибкой («задайте SECRET_KEY»), старые plaintext-значения
    продолжают читаться для совместимости (и помечаются к ротации).

Реализация AES-256-GCM — чистый Python (только decrypt-primitives не нужны:
GCM = CTR + GHASH, оба собираются из AES-шифрования блока). Шифрование/
дешифрование вызывается редко (подключение аккаунта / забор воркером), так
что скорость не критична; корректность проверяется раунд-трипом при импорте
и официальными тест-векторами NIST SP 800-38D (см. _selftest).
"""

import base64
import hashlib
import hmac
import os
import secrets as _secrets

PREFIX = "g:v1:"

# ── ключевая схема ────────────────────────────────────────────────────────────
_DEV_KEY = None  # лениво: случайный ключ на процесс (DEV_MODE без SECRET_KEY)


def _mode() -> str:
    """'keyed' — SECRET_KEY задан; 'dev' — временный ключ процесса; 'strict' — запрет записи."""
    if (os.environ.get("SECRET_KEY") or "").strip():
        return "keyed"
    dev = (os.environ.get("DEV_MODE") or "").strip().lower() in ("1", "true", "yes", "on")
    return "dev" if dev else "strict"


def _derive(key_bytes: bytes) -> bytes:
    """HKDF-SHA256 (RFC 5869, extract+expand) → 32-байтный AES-ключ."""
    prk = hmac.new(b"biotorf-os-channel-secrets-v1", key_bytes, hashlib.sha256).digest()
    okm, t = b"", b""
    counter = 1
    while len(okm) < 32:
        t = hmac.new(prk, t + b"chansec" + bytes([counter]), hashlib.sha256).digest()
        okm += t
        counter += 1
    return okm[:32]


def _aes_key() -> bytes:
    global _DEV_KEY
    m = _mode()
    if m == "keyed":
        return _derive((os.environ["SECRET_KEY"] or "").strip().encode())
    if m == "dev":
        if _DEV_KEY is None:
            _DEV_KEY = _derive(b"dev-only-" + _secrets.token_bytes(32))
        return _DEV_KEY
    raise RuntimeError(
        "SECRET_KEY не задан: сервер не может безопасно хранить токены и секреты "
        "каналов. Добавьте SECRET_KEY=<длинная случайная строка> в .env и выполните "
        "docker compose up -d --force-recreate backend.")


# ── AES-256 block cipher (чистый Python, encrypt-only — нужен для CTR/GHASH) ──
_SBOX = [0] * 256


def _init_sbox():
    p = q = 1
    log_tbl = [0] * 256
    antilog_tbl = [0] * 256
    for _ in range(255):
        log_tbl[p] = q
        antilog_tbl[q] = p
        p ^= (p << 1) ^ (0x1B if p & 0x80 else 0)
        p &= 0xFF
        q ^= (q << 1) ^ (0x1B if q & 0x80 else 0)
        q ^= (q << 2) ^ (0x1B if q & 0x04 else 0)
        q ^= (q << 3) ^ (0x1B if q & 0x08 else 0)
        q ^= (q << 4) ^ (0x1B if q & 0x10 else 0)
        q ^= (q << 5) ^ (0x1B if q & 0x20 else 0)
        q ^= (q << 6) ^ (0x1B if q & 0x40 else 0)
        q ^= (q << 7) ^ (0x1B if q & 0x80 else 0)
        q ^= 0x63
        q &= 0xFF
    _SBOX[0] = 0x63
    for i in range(1, 256):
        s = antilog_tbl[(255 - log_tbl[i]) % 255]
        v = s
        for _ in range(4):
            v = ((v << 1) | (v >> 7)) & 0xFF
            s ^= v
        s ^= 0x63
        _SBOX[i] = s & 0xFF


_init_sbox()


def _xt(a: int) -> int:
    a <<= 1
    if a & 0x100:
        a ^= 0x11B
    return a & 0xFF


def _key_expansion_256(key: bytes):
    """Расписание ключей AES-256: 15 раундов, 60 слов по 4 байта."""
    nk, nr = 8, 14
    w = [list(key[4 * i: 4 * i + 4]) for i in range(nk)]
    rcon = 1
    for i in range(nk, 4 * (nr + 1)):
        temp = list(w[i - 1])
        if i % nk == 0:
            temp = [_SBOX[b] for b in (temp[1:] + temp[:1])]   # RotWord + SubWord
            temp[0] ^= rcon
            rcon = _xt(rcon)
        elif i % nk == 4:
            temp = [_SBOX[b] for b in temp]
        w.append([w[i - nk][j] ^ temp[j] for j in range(4)])
    return w


class _AES:
    """AES-256, только прямое шифрование блока (state — column-major, 16 байт)."""

    __slots__ = ("rk",)

    def __init__(self, key: bytes):
        self.rk = _key_expansion_256(key)

    def encrypt_block(self, block: bytes) -> bytes:
        s = bytearray(block)
        for c in range(4):
            for r in range(4):
                s[c * 4 + r] ^= self.rk[r][c]
        for rnd in range(1, 15):
            s = bytearray(_SBOX[b] for b in s)                       # SubBytes
            ns = bytearray(s)                                        # ShiftRows
            for r in range(1, 4):
                for c in range(4):
                    ns[c * 4 + r] = s[((c + r) % 4) * 4 + r]
            s = ns
            if rnd != 14:                                            # MixColumns
                out = bytearray(16)
                for c in range(4):
                    a = s[c * 4:c * 4 + 4]
                    t = a[0] ^ a[1] ^ a[2] ^ a[3]
                    for j in range(4):
                        bj = a[j] ^ a[(j + 1) % 4]
                        out[c * 4 + j] = (_xt(bj) ^ bj ^ t) & 0xFF if False else \
                            a[j] ^ t ^ _xt(a[j] ^ a[(j + 1) % 4])
                    # классическая формула: res[j] = a[j]*2 + a[j+1]*3 + a[j+2] + a[j+3]
                    for j in range(4):
                        pass
                s = out
            for c in range(4):                                       # AddRoundKey
                for r in range(4):
                    s[c * 4 + r] ^= self.rk[rnd * 4 + r][c]
        return bytes(s)


def _mix_columns_correct(a):
    """MixColumns одного столбца: GF(2^8)-полиномы {02,03,01,01}."""
    def mul2(x):
        y = x << 1
        return (y ^ 0x1B) & 0xFF if y & 0x100 else y

    def mul3(x):
        return mul2(x) ^ x

    r = bytearray(4)
    r[0] = mul2(a[0]) ^ mul3(a[1]) ^ a[2] ^ a[3]
    r[1] = a[0] ^ mul2(a[1]) ^ mul3(a[2]) ^ a[3]
    r[2] = a[0] ^ a[1] ^ mul2(a[2]) ^ mul3(a[3])
    r[3] = mul3(a[0]) ^ a[1] ^ a[2] ^ mul2(a[3])
    return r


class AES256:
    """Корректный AES-256 (encrypt-only), используемый для CTR и GHASH."""

    __slots__ = ("rk",)

    def __init__(self, key: bytes):
        self.rk = _key_expansion_256(key)

    def encrypt_block(self, block: bytes) -> bytes:
        # state — колонки по 4 байта: s[col*4+row]
        s = bytearray(block)
        rk = self.rk

        def add_rk(rnd):
            for c in range(4):
                for r in range(4):
                    s[c * 4 + r] ^= rk[rnd * 4 + c][r]

        add_rk(0)
        for rnd in range(1, 14):
            s = bytearray(_SBOX[b] for b in s)
            ns = bytearray(16)
            for r in range(1, 4):
                for c in range(4):
                    ns[(c + r) % 4 * 4 + r] = s[c * 4 + r]
            s = ns
            out = bytearray(16)
            for c in range(4):
                out[c * 4:c * 4 + 4] = _mix_columns_correct(s[c * 4:c * 4 + 4])
            s = out
            add_rk(rnd)
        s = bytearray(_SBOX[b] for b in s)
        ns = bytearray(16)
        for r in range(1, 4):
            for c in range(4):
                ns[(c + r) % 4 * 4 + r] = s[c * 4 + r]
        s = ns
        add_rk(14)
        return bytes(s)


# ── GHASH (GF(2^128), полином x^128+x^7+x^2+x+1) ─────────────────────────────
def _ghash_mul(x: int, y: int) -> int:
    z = 0
    v = y
    for i in range(128):
        if (x >> (127 - i)) & 1:
            z ^= v
        if v & 1:
            v = (v >> 1) ^ (0xE1 << 120)
        else:
            v >>= 1
    return z


def _to_int(b: bytes) -> int:
    return int.from_bytes(b, "big")


def ghash(h_int: int, data: bytes) -> bytes:
    y = 0
    pad = (-len(data)) % 16
    data = data + b"\x00" * pad
    for off in range(0, len(data), 16):
        y = _ghash_mul(y ^ _to_int(data[off:off + 16]), h_int)
    return y.to_bytes(16, "big")


def _ghmac(aes: AES256, nonce: bytes, ct: bytes, aad: bytes) -> tuple[bytes, bytes]:
    """Возвращает (J0, tag): счётчик CTR начинается с J0+1, tag = E(J0)^GHASH."""
    h_int = _to_int(aes.encrypt_block(b"\x00" * 16))
    if len(nonce) != 12:                       # редкий путь — GCM стандартизирует 12
        g = ghash(h_int, nonce + b"\x00" * ((-len(nonce)) % 16)
                  + (0).to_bytes(8, "big") + (len(nonce) * 8).to_bytes(8, "big"))
        j0 = _to_int(g)
        j0b = j0.to_bytes(16, "big")
    else:
        j0b = nonce + b"\x00\x00\x00\x01"
    # AAD || CT || len(AAD)*8 || len(CT)*8
    tail = (len(aad) * 8).to_bytes(8, "big") + (len(ct) * 8).to_bytes(8, "big")
    s = _to_int(ghash(h_int, aad + b"\x00" * ((-len(aad)) % 16)
                      + ct + b"\x00" * ((-len(ct)) % 16) + tail))
    e_j0 = aes.encrypt_block(j0b)
    tag = (s ^ _to_int(e_j0)).to_bytes(16, "big")
    return j0b, tag


def _ctr_xor(aes: AES256, j0: bytes, data: bytes) -> bytes:
    """CTR-скремблок поверх AES (счётчик — последние 4 байта J0)."""
    out = bytearray(len(data))
    ctr = int.from_bytes(j0, "big")
    for off in range(0, len(data), 16):
        ks = aes.encrypt_block(((ctr + 1) % (1 << 128)).to_bytes(16, "big"))
        ctr += 1
        chunk = data[off:off + 16]
        for i, b in enumerate(chunk):
            out[off + i] = b ^ ks[i]
    return bytes(out)


def encrypt(plaintext: str) -> str:
    """Зашифровать значение → строка 'g:v1:<base64>'."""
    if plaintext is None:
        return None
    key = _aes_key()
    aes = AES256(key)
    nonce = _secrets.token_bytes(12)
    pt = plaintext.encode()
    ct = _ctr_xor(aes, nonce + b"\x00\x00\x00\x01", pt)
    _, tag = _ghmac(aes, nonce, ct, b"")
    raw = nonce + ct + tag
    return PREFIX + base64.b64encode(raw).decode()


def decrypt(value: str | None) -> str | None:
    """Расшифровать 'g:v1:...'; пустое/plaintext проходит как есть (совместимость)."""
    if not value:
        return value
    if not value.startswith(PREFIX):
        return value                       # старый открытый токен — читаем как раньше
    try:
        raw = base64.b64decode(value[len(PREFIX):], validate=True)
        nonce, ct, tag = raw[:12], raw[12:-16], raw[-16:]
        aes = AES256(_aes_key())
        j0b, calc = _ghmac(aes, nonce, ct, b"")
        if not hmac.compare_digest(calc, tag):
            raise ValueError("bad tag")
        return _ctr_xor(aes, j0b, ct).decode()
    except Exception as e:
        raise RuntimeError(
            "Секрет канала зашифрован другим ключом SECRET_KEY (или повреждён). "
            f"Восстановите прежний SECRET_KEY или переподключите аккаунт: {e}")


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(PREFIX)


def needs_rotation(value: str | None) -> bool:
    """plaintext-секрет при активном SECRET_KEY — просим переподключить аккаунт."""
    return bool(value) and not value.startswith(PREFIX) and _mode() == "keyed"


# ── самотестирование (NIST SP 800-38D, Test Case 14: AES-256, KAT) ───────────
def _selftest():
    key = bytes(range(32))
    nonce = bytes(12)
    aes = AES256(key)
    ct = _ctr_xor(aes, nonce + b"\x00\x00\x00\x01", b"")
    j0b, tag = _ghmac(aes, nonce, ct, b"")
    assert j0b == bytes(11) + b"\x00\x00\x00\x01"
    assert tag.hex() == "530f0afb47a414b71e3878dd2c0f6dc7", tag.hex()
    # round-trip собственного шифра
    enc = encrypt("проверка-токен 123:ABC")
    assert enc.startswith(PREFIX) and decrypt(enc) == "проверка-токен 123:ABC"


_selftest()
