import os
import base64
import logging
import stat
from typing import Optional

logger = logging.getLogger(__name__)

_FERNET_KEY = None
_FERNET_CIPHER = None
_FALLBACK_XOR_KEY = None

_ENC_PREFIX = "fenc:"
_FALLBACK_SUBMARK = "0:"
_NONE_SENTINEL = "\x00__NONE_SENTINEL__\x00"


def _load_or_create_fernet_key():
    global _FERNET_KEY, _FERNET_CIPHER, _FALLBACK_XOR_KEY

    if _FERNET_KEY is not None or _FALLBACK_XOR_KEY is not None:
        return

    env_key = os.environ.get("CONFIG_ENCRYPTION_KEY")
    if env_key:
        try:
            from cryptography.fernet import Fernet

            _FERNET_CIPHER = Fernet(env_key.encode("utf-8"))
            _FERNET_KEY = env_key
            logger.info("Fernet key loaded from CONFIG_ENCRYPTION_KEY env var")
            return
        except Exception as e:
            logger.warning("Failed to use CONFIG_ENCRYPTION_KEY: %s", e)
            _FERNET_KEY = None
            _FERNET_CIPHER = None

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    key_path = os.path.join(project_root, "config", ".config.key")

    try:
        if os.path.exists(key_path):
            try:
                with open(key_path, "r", encoding="utf-8") as f:
                    file_key = f.read().strip()
                if file_key:
                    from cryptography.fernet import Fernet

                    _FERNET_CIPHER = Fernet(file_key.encode("utf-8"))
                    _FERNET_KEY = file_key
                    logger.info("Fernet key loaded from config/.config.key")
                    return
            except Exception as e:
                logger.warning("Failed to load key from config/.config.key: %s", e)

        try:
            from cryptography.fernet import Fernet

            new_key = Fernet.generate_key().decode("utf-8")
            os.makedirs(os.path.dirname(key_path), exist_ok=True)
            fd = os.open(
                key_path,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                stat.S_IRUSR | stat.S_IWUSR,
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(new_key)
            except Exception:
                try:
                    os.close(fd)
                except Exception:
                    pass
                raise
            try:
                os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)
            except Exception:
                pass
            _FERNET_CIPHER = Fernet(new_key.encode("utf-8"))
            _FERNET_KEY = new_key
            logger.info("Fernet key generated and saved to config/.config.key")
            return
        except Exception as e:
            logger.warning("Failed to generate/save Fernet key: %s", e)
    except Exception as e:
        logger.warning("Fernet key path processing failed: %s", e)

    logger.warning("Fernet not available, falling back to XOR obfuscation mode")
    _FALLBACK_XOR_KEY = _stable_xor_key()


def _stable_xor_key():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = []
    key_path = os.path.join(project_root, "config", ".config.key")
    if os.path.exists(key_path):
        try:
            with open(key_path, "rb") as f:
                candidates.append(f.read())
        except Exception:
            pass
    env_key = os.environ.get("CONFIG_ENCRYPTION_KEY")
    if env_key:
        candidates.append(env_key.encode("utf-8"))
    candidates.append(b"investment-compass-fallback-xor-key-v1")
    raw = b"|".join(candidates)
    result = bytearray(32)
    for i, b in enumerate(raw):
        result[i % 32] ^= b
    return bytes(result)


def _xor_bytes(data: bytes, key: bytes) -> bytes:
    klen = len(key)
    return bytes(b ^ key[i % klen] for i, b in enumerate(data))


def encrypt_str(plain) -> str:
    _load_or_create_fernet_key()

    is_none = False
    if plain is None:
        is_none = True
        plain = _NONE_SENTINEL
    if not isinstance(plain, str):
        plain = str(plain)

    plain_bytes = plain.encode("utf-8")

    if _FERNET_CIPHER is not None:
        try:
            token = _FERNET_CIPHER.encrypt(plain_bytes)
            return _ENC_PREFIX + token.decode("utf-8")
        except Exception as e:
            logger.warning("Fernet encrypt failed, falling back: %s", e)

    assert _FALLBACK_XOR_KEY is not None
    xored = _xor_bytes(plain_bytes, _FALLBACK_XOR_KEY)
    b64 = base64.urlsafe_b64encode(xored).decode("utf-8")
    return _ENC_PREFIX + _FALLBACK_SUBMARK + b64


def decrypt_str(enc):
    if enc is None:
        return None
    if enc == "":
        return ""
    if not isinstance(enc, str):
        logger.warning("decrypt_str received non-str input, returning None")
        return None

    _load_or_create_fernet_key()

    token_part = enc
    if token_part.startswith(_ENC_PREFIX):
        token_part = token_part[len(_ENC_PREFIX):]

    if _FERNET_CIPHER is not None:
        try:
            plain_bytes = _FERNET_CIPHER.decrypt(token_part.encode("utf-8"))
            result = plain_bytes.decode("utf-8")
            if result == _NONE_SENTINEL:
                return None
            return result
        except Exception:
            pass

    if token_part.startswith(_FALLBACK_SUBMARK):
        try:
            b64_part = token_part[len(_FALLBACK_SUBMARK):]
            xored = base64.urlsafe_b64decode(b64_part.encode("utf-8"))
            assert _FALLBACK_XOR_KEY is not None
            plain_bytes = _xor_bytes(xored, _FALLBACK_XOR_KEY)
            result = plain_bytes.decode("utf-8")
            if result == _NONE_SENTINEL:
                return None
            return result
        except Exception as e:
            logger.warning("XOR fallback decrypt failed: %s", e)
            return None

    logger.warning("decrypt_str failed: no method could decode the input")
    return None


def mask_api_key(key: Optional[str]) -> str:
    if not key:
        return ""
    k = key.strip()
    if len(k) <= 8:
        return "*" * len(k)
    return k[:4] + "*" * (len(k) - 8) + k[-4:]
