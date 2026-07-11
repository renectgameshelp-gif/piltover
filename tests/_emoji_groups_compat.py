from io import BytesIO
from typing import Self

from piltover.tl import EmojiGroup, EmojiGroupGreeting, EmojiGroupPremium
from piltover.tl.functions.messages import (
    GetEmojiGroups,
    GetEmojiProfilePhotoGroups,
    GetEmojiStatusGroups,
    GetEmojiStickerGroups,
)
from piltover.tl.types.messages import EmojiGroups


class GetEmojiStickerGroupsCompat(GetEmojiStickerGroups):
    QUALNAME = GetEmojiStickerGroups.__tl_name__
    RESTORE_CLS = GetEmojiStickerGroups

    def __len__(self) -> int:
        return len(self.write())

    @classmethod
    def read(cls, stream: BytesIO) -> Self:
        return cls.deserialize(stream)


class GetEmojiGroupsCompat(GetEmojiGroups):
    QUALNAME = GetEmojiGroups.__tl_name__
    RESTORE_CLS = GetEmojiGroups

    def __len__(self) -> int:
        return len(self.write())

    @classmethod
    def read(cls, stream: BytesIO) -> Self:
        return cls.deserialize(stream)


class GetEmojiStatusGroupsCompat(GetEmojiStatusGroups):
    QUALNAME = GetEmojiStatusGroups.__tl_name__
    RESTORE_CLS = GetEmojiStatusGroups

    def __len__(self) -> int:
        return len(self.write())

    @classmethod
    def read(cls, stream: BytesIO) -> Self:
        return cls.deserialize(stream)


class GetEmojiProfilePhotoGroupsCompat(GetEmojiProfilePhotoGroups):
    QUALNAME = GetEmojiProfilePhotoGroups.__tl_name__
    RESTORE_CLS = GetEmojiProfilePhotoGroups

    def __len__(self) -> int:
        return len(self.write())

    @classmethod
    def read(cls, stream: BytesIO) -> Self:
        return cls.deserialize(stream)


class EmojiGroupsCompat(EmojiGroups):
    QUALNAME = EmojiGroups.__tl_name__
    RESTORE_CLS = EmojiGroups

    def __len__(self) -> int:
        return len(self.write())

    @classmethod
    def read(cls, stream: BytesIO) -> Self:
        return cls.deserialize(stream)


class EmojiGroupCompat(EmojiGroup):
    QUALNAME = EmojiGroup.__tl_name__
    RESTORE_CLS = EmojiGroup

    def __len__(self) -> int:
        return len(self.write())

    @classmethod
    def read(cls, stream: BytesIO) -> Self:
        return cls.deserialize(stream)


class EmojiGroupGreetingCompat(EmojiGroupGreeting):
    QUALNAME = EmojiGroupGreeting.__tl_name__
    RESTORE_CLS = EmojiGroupGreeting

    def __len__(self) -> int:
        return len(self.write())

    @classmethod
    def read(cls, stream: BytesIO) -> Self:
        return cls.deserialize(stream)


class EmojiGroupPremiumCompat(EmojiGroupPremium):
    QUALNAME = EmojiGroupPremium.__tl_name__
    RESTORE_CLS = EmojiGroupPremium

    def __len__(self) -> int:
        return len(self.write())

    @classmethod
    def read(cls, stream: BytesIO) -> Self:
        return cls.deserialize(stream)