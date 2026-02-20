"""
signer.py — Digital signing for redacted PDFs using ECDSA P-256.
Appends a SHA-256 hash + ECDSA signature as PDF metadata.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend

import fitz  # pymupdf

logger = logging.getLogger(__name__)

_KEY_FILENAME = "signing_key.pem"


class DocumentSigner:
    """Signs redacted documents using ECDSA P-256."""

    def __init__(self, keys_dir: str):
        self.keys_dir = Path(keys_dir)
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        self._private_key = self._load_or_generate_key()

    def sign(self, input_path: Path, output_path: Path) -> Path:
        """
        Hash the input PDF and embed the signature as PDF metadata.
        Returns the output path.
        """
        # Read file bytes and compute SHA-256
        data = input_path.read_bytes()
        file_hash = hashlib.sha256(data).hexdigest()

        # ECDSA signature over the hash
        signature = self._private_key.sign(
            file_hash.encode(),
            ec.ECDSA(hashes.SHA256()),
        )

        # Open PDF and embed signature in metadata
        doc = fitz.open(str(input_path))
        metadata = doc.metadata or {}
        metadata["keywords"] = json.dumps({
            "secure_doc_ai_signature": signature.hex(),
            "sha256": file_hash,
            "signed_at": datetime.now(timezone.utc).isoformat(),
            "algorithm": "ECDSA-P256-SHA256",
        })
        doc.set_metadata(metadata)
        doc.save(str(output_path), garbage=4, deflate=True)
        doc.close()

        logger.info("Signed %s → %s (hash=%s…)", input_path.name, output_path.name, file_hash[:12])
        return output_path

    def verify(self, file_path: Path) -> bool:
        """Verify the embedded signature is valid."""
        doc = fitz.open(str(file_path))
        metadata = doc.metadata or {}
        doc.close()

        try:
            sig_data = json.loads(metadata.get("keywords", "{}"))
            stored_sig = bytes.fromhex(sig_data["secure_doc_ai_signature"])
            stored_hash = sig_data["sha256"]
        except (json.JSONDecodeError, KeyError):
            logger.warning("No valid signature found in %s", file_path.name)
            return False

        # Verify
        public_key = self._private_key.public_key()
        try:
            public_key.verify(stored_sig, stored_hash.encode(), ec.ECDSA(hashes.SHA256()))
            return True
        except Exception:
            logger.warning("Signature verification FAILED for %s", file_path.name)
            return False

    # ── Key management ───────────────────────────────────────────────────

    def _load_or_generate_key(self) -> ec.EllipticCurvePrivateKey:
        key_path = self.keys_dir / _KEY_FILENAME

        if key_path.exists():
            pem = key_path.read_bytes()
            key = serialization.load_pem_private_key(pem, password=None, backend=default_backend())
            logger.info("Loaded existing signing key from %s", key_path)
            return key

        # Generate new P-256 key
        key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_path.write_bytes(pem)
        logger.info("Generated new ECDSA P-256 signing key → %s", key_path)
        return key
