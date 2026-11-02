import hashlib
import platform
import ssl
from dataclasses import dataclass
from pathlib import Path

CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class FileHashes:
    sha256: str
    md5: str
    size_bytes: int


class FileHasher:
    """Computes SHA-256 and MD5 in one pass over a stream."""

    def __init__(self) -> None:
        self._sha256 = hashlib.sha256()
        self._md5 = hashlib.md5(usedforsecurity=False)
        self.size_bytes = 0

    def update(self, chunk: bytes) -> None:
        self._sha256.update(chunk)
        self._md5.update(chunk)
        self.size_bytes += len(chunk)

    def result(self) -> FileHashes:
        return FileHashes(self._sha256.hexdigest(), self._md5.hexdigest(), self.size_bytes)


def hash_file(path: Path) -> FileHashes:
    hasher = FileHasher()
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_SIZE):
            hasher.update(chunk)
    return hasher.result()


def hashlib_version() -> str:
    return f"Python {platform.python_version()}, {ssl.OPENSSL_VERSION}"
