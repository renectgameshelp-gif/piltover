from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SearchFilters:
    kind: str
    show_system: bool = False
    include_deleted: bool = False
    channel_kind: str = "all"  # all | channel | supergroup

    def encode(self) -> bytes:
        flags: list[str] = []
        if self.show_system:
            flags.append("sys")
        if self.include_deleted:
            flags.append("del")
        if self.kind == "ch" and self.channel_kind != "all":
            flags.append(self.channel_kind)
        if not flags:
            return self.kind.encode()
        return f"{self.kind}:{','.join(flags)}".encode()

    @classmethod
    def decode(cls, data: bytes | None) -> SearchFilters:
        if not data:
            return cls(kind="user")
        text = data.decode()
        if ":" not in text:
            return cls(kind=text)
        kind, flags_raw = text.split(":", 1)
        flags = {part.strip() for part in flags_raw.split(",") if part.strip()}
        channel_kind = "all"
        if "channel" in flags:
            channel_kind = "channel"
            flags.discard("channel")
        elif "supergroup" in flags:
            channel_kind = "supergroup"
            flags.discard("supergroup")
        return cls(
            kind=kind,
            show_system="sys" in flags,
            include_deleted="del" in flags,
            channel_kind=channel_kind,
        )

    def toggle(self, flag: str) -> None:
        if flag == "sys":
            self.show_system = not self.show_system
        elif flag == "del":
            self.include_deleted = not self.include_deleted
        elif flag == "channel":
            self.channel_kind = {
                "all": "channel",
                "channel": "supergroup",
                "supergroup": "all",
            }[self.channel_kind]