"""
Godot 4 PCK File Reader for Slay the Spire 2.
Directly reads files and manifests from SlayTheSpire2.pck without external Godot dependencies.
"""

import os
import struct
from typing import Dict, List, Optional, Tuple


class PckEntry:
    def __init__(self, path: str, offset: int, size: int, md5: bytes, flags: int):
        self.path = path
        self.offset = offset
        self.size = size
        self.md5 = md5
        self.flags = flags

    def __repr__(self) -> str:
        return f"<PckEntry path='{self.path}' size={self.size} offset={self.offset}>"


class GodotPckReader:
    def __init__(self, pck_path: str):
        self.pck_path = pck_path
        self.file_base = 0
        self.version = 0
        self.engine_version = (0, 0, 0)
        self.entries: Dict[str, PckEntry] = {}
        self._load_index()

    def _load_index(self) -> None:
        if not os.path.exists(self.pck_path):
            raise FileNotFoundError(f"PCK file not found: {self.pck_path}")

        with open(self.pck_path, "rb") as f:
            magic = f.read(4)
            if magic != b"GDPC":
                raise ValueError(f"Invalid PCK magic: {magic}")

            self.version, major, minor, patch = struct.unpack("<IIII", f.read(16))
            self.engine_version = (major, minor, patch)
            flags = struct.unpack("<I", f.read(4))[0]
            self.file_base = struct.unpack("<Q", f.read(8))[0]
            
            # Read header to find directory offset
            # In Godot 4 v3 PCK, directory offset is at byte 28 (or 0x713dad30)
            f.seek(28)
            dir_offset = struct.unpack("<Q", f.read(8))[0]
            if dir_offset == 0 or dir_offset > os.path.getsize(self.pck_path):
                # Fallback search for directory offset
                dir_offset = 0x713dad30

            f.seek(dir_offset)
            file_count = struct.unpack("<I", f.read(4))[0]

            for _ in range(file_count):
                path_len = struct.unpack("<I", f.read(4))[0]
                raw_path = f.read(path_len)
                path = raw_path.rstrip(b"\x00").decode("utf-8", errors="replace")
                offset, size = struct.unpack("<QQ", f.read(16))
                md5 = f.read(16)
                entry_flags = struct.unpack("<I", f.read(4))[0]
                entry = PckEntry(path, offset, size, md5, entry_flags)
                self.entries[path] = entry

    def get_file_content(self, path: str) -> Optional[bytes]:
        entry = self.entries.get(path)
        if not entry:
            return None
        with open(self.pck_path, "rb") as f:
            f.seek(entry.offset + self.file_base)
            return f.read(entry.size)

    def get_text(self, path: str, encoding: str = "utf-8") -> Optional[str]:
        raw = self.get_file_content(path)
        if raw is None:
            return None
        return raw.decode(encoding, errors="replace")

    def find_files(self, pattern_or_substr: str) -> List[str]:
        sub = pattern_or_substr.lower()
        return [p for p in self.entries if sub in p.lower()]
