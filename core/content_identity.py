# -*- coding: utf-8 -*-
"""GP002 dual-hash identity primitive（纯函数，无状态）。

职责分离：
- byte sha256（Note.sha256 / provenance / evidence / conflict）：磁盘字节是否变化；
- content identity（本模块）：知识生产视角下是否同一份内容——只规范化
  BOM 与 CRLF/CR/LF 差异（GP002 实证：Sample A 的 CRLF→LF 漂移）。

本模块禁止：访问 Vault/processed-index/receipts、读写文件、读取 config。
"""
from __future__ import annotations

import hashlib

BYTE_MATCH = "BYTE_MATCH"
IDENTITY_MATCH = "IDENTITY_MATCH"
REPRESENTATION_DRIFT = "REPRESENTATION_DRIFT"
NO_MATCH = "NO_MATCH"

_MATCH_KINDS = {BYTE_MATCH, IDENTITY_MATCH, REPRESENTATION_DRIFT}


def canonicalize_content_bytes(raw: bytes) -> str:
    """GP002 契约：decode UTF-8-sig → CRLF/CR → LF。不做任何其他规范化。

    ``surrogateescape`` keeps malformed UTF-8 bytes distinct. Replacement
    decoding would collapse different invalid byte sequences to U+FFFD and
    could falsely treat changed source bytes as the same content.
    """
    return raw.decode("utf-8-sig", errors="surrogateescape").replace("\r\n", "\n").replace("\r", "\n")


def content_identity_sha256(raw: bytes) -> str:
    return hashlib.sha256(
        canonicalize_content_bytes(raw).encode("utf-8", errors="surrogateescape")
    ).hexdigest()


def representation_variant_hashes(canonical_text: str) -> dict[str, str]:
    """当前 canonical 内容的有限、明确允许的 byte 表示（白名单，不做任何猜测）。"""
    utf8 = canonical_text.encode("utf-8", errors="surrogateescape")
    return {
        "UTF8+LF": hashlib.sha256(utf8).hexdigest(),
        "UTF8+CRLF": hashlib.sha256(
            canonical_text.replace("\n", "\r\n").encode(
                "utf-8", errors="surrogateescape")).hexdigest(),
        "UTF8+BOM+LF": hashlib.sha256(b"\xef\xbb\xbf" + utf8).hexdigest(),
        "UTF8+BOM+CRLF": hashlib.sha256(
            b"\xef\xbb\xbf" + canonical_text.replace("\n", "\r\n").encode(
                "utf-8", errors="surrogateescape")).hexdigest(),
    }


def match_content_identity(stored_byte_sha256: str | None,
                           stored_content_identity_sha256: str | None,
                           current_bytes: bytes) -> dict[str, str | None]:
    """判定 stored 版本与 current 字节的关系（结构化结果，绝不静默合并 kind）。"""
    current_byte = hashlib.sha256(current_bytes).hexdigest()
    if stored_byte_sha256 and stored_byte_sha256 == current_byte:
        return {"kind": BYTE_MATCH, "reason": "stored byte hash matches current bytes",
                "variant": None}
    if (stored_content_identity_sha256
            and stored_content_identity_sha256 == content_identity_sha256(current_bytes)):
        return {"kind": IDENTITY_MATCH,
                "reason": "stored content identity matches current canonical content",
                "variant": None}
    canonical_text = canonicalize_content_bytes(current_bytes)
    for name, variant_hash in representation_variant_hashes(canonical_text).items():
        if stored_byte_sha256 and variant_hash == stored_byte_sha256:
            return {"kind": REPRESENTATION_DRIFT,
                    "reason": f"stored byte hash matches allowed representation variant {name}",
                    "variant": name}
    return {"kind": NO_MATCH, "reason": "stored version matches neither bytes nor canonical content",
            "variant": None}


def stored_version_covers(stored_byte_sha256: str | None,
                          stored_content_identity_sha256: str | None,
                          current_bytes: bytes | None) -> bool:
    """接线便捷判断：stored 版本是否覆盖当前内容（用于 receipt/processed-index 匹配）。"""
    if current_bytes is None:
        return False
    return match_content_identity(
        stored_byte_sha256, stored_content_identity_sha256, current_bytes)["kind"] in _MATCH_KINDS
