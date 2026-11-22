"""Authenticated encryption at rest for OAuth tokens, webhook secrets, and MFA seeds.

Uses AES-256-GCM (via `cryptography`) whenever installed — which is pinned in
`scripts/vps/api-requirements.lock` for production — and falls back to an authenticated
Encrypt-then-MAC SHA-256-CTR + HMAC-SHA256 construction (`enc:v1:sctr:...`) only when running
in minimal local dev environments without `cryptography`. Both formats decrypt transparently,
and legacy plaintext values can still be read during migration when `allow_plaintext=True`.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct

from .config import get_settings

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM as _AESGCM
except ImportError:  # pragma: no cover - production installs cryptography==50.0.2
    _AESGCM = None

PREFIX_GCM = "enc:v1:aesgcm:"
PREFIX_SCTR = "enc:v1:sctr:"
_DEV_FALLBACK_KEY = b"trendi-concierge-dev-ephemeral-vault-key-v1"


def _derive_key(purpose: str = "vault") -> bytes:
    settings = get_settings()
    raw = (settings.token_encryption_key or "").strip()
    if raw:
        material = raw.encode("utf-8")
    elif (settings.admin_token or "").strip():
        material = settings.admin_token.strip().encode("utf-8")
    else:
        material = _DEV_FALLBACK_KEY
    return hashlib.sha256(b"trendi:vault:v1:" + purpose.encode("utf-8") + b":" + material).digest()


def _sctr_keystream(enc_key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        out.extend(hmac.new(enc_key, nonce + struct.pack(">I", counter), hashlib.sha256).digest())
        counter += 1
    return bytes(out[:length])


def is_encrypted(value: str | None) -> bool:
    if not isinstance(value, str):
        return False
    return value.startswith(PREFIX_GCM) or value.startswith(PREFIX_SCTR)


def encrypt_text(plaintext: str, *, aad: str = "") -> str:
    """Encrypt UTF-8 plaintext and return a versioned ASCII envelope."""
    data = plaintext.encode("utf-8")
    aad_bytes = aad.encode("utf-8")
    if _AESGCM is not None:
        key = _derive_key("aesgcm")
        nonce = os.urandom(12)
        ct = _AESGCM(key).encrypt(nonce, data, aad_bytes)
        return PREFIX_GCM + base64.urlsafe_b64encode(nonce + ct).decode("ascii")
    enc_key = _derive_key("sctr-enc")
    mac_key = _derive_key("sctr-mac")
    nonce = secrets.token_bytes(16)
    ks = _sctr_keystream(enc_key, nonce, len(data))
    ct = bytes(a ^ b for a, b in zip(data, ks))
    tag = hmac.new(mac_key, nonce + aad_bytes + struct.pack(">Q", len(aad_bytes)) + ct, hashlib.sha256).digest()
    return PREFIX_SCTR + base64.urlsafe_b64encode(nonce + tag + ct).decode("ascii")


def decrypt_text(value: str, *, aad: str = "", allow_plaintext: bool = True) -> str:
    """Decrypt a versioned envelope. Raises ValueError on tampering or wrong key/AAD."""
    if not isinstance(value, str):
        raise ValueError("Encrypted value must be a string")
    aad_bytes = aad.encode("utf-8")
    if value.startswith(PREFIX_GCM):
        if _AESGCM is None:
            raise ValueError("AES-GCM envelope requires cryptography package")
        raw = base64.urlsafe_b64decode(value[len(PREFIX_GCM):].encode("ascii"))
        if len(raw) < 12 + 16:
            raise ValueError("Truncated AES-GCM payload")
        nonce, ct = raw[:12], raw[12:]
        try:
            pt = _AESGCM(_derive_key("aesgcm")).decrypt(nonce, ct, aad_bytes)
        except Exception as exc:
            raise ValueError("Decryption failed") from exc
        return pt.decode("utf-8")
    if value.startswith(PREFIX_SCTR):
        raw = base64.urlsafe_b64decode(value[len(PREFIX_SCTR):].encode("ascii"))
        if len(raw) < 16 + 32:
            raise ValueError("Truncated SCTR payload")
        nonce, tag, ct = raw[:16], raw[16:48], raw[48:]
        mac_key = _derive_key("sctr-mac")
        expected = hmac.new(mac_key, nonce + aad_bytes + struct.pack(">Q", len(aad_bytes)) + ct, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            raise ValueError("Decryption authentication failed")
        enc_key = _derive_key("sctr-enc")
        ks = _sctr_keystream(enc_key, nonce, len(ct))
        pt = bytes(a ^ b for a, b in zip(ct, ks))
        return pt.decode("utf-8")
    if allow_plaintext:
        return value
    raise ValueError("Unencrypted value rejected")
