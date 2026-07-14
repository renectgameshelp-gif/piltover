from __future__ import annotations

import re

from piltover.db.models import Bot, Channel, Chat, User, Username

_PHONE_RE = re.compile(r"^\+?\d{5,20}$")
_ID_RE = re.compile(r"^\d+$")


def _normalize_phone(raw: str) -> str:
    return "".join(ch for ch in raw if ch.isdigit())


async def resolve_user_query(
        query: str, *, include_deleted: bool = False, include_system: bool = True,
) -> User | None:
    text = query.strip()
    if not text:
        return None
    if text.startswith("@"):
        text = text[1:]

    base = User.all() if include_deleted else User.filter(deleted=False)
    if not include_system:
        base = base.filter(system=False)
    base = base.filter(bot=False)

    if _PHONE_RE.match(text):
        return await base.get_or_none(phone_number=_normalize_phone(text))
    if _ID_RE.match(text):
        return await base.get_or_none(id=int(text))

    username_row = await Username.get_or_none(username__iexact=text).select_related("user")
    if username_row is None or username_row.user_id is None:
        return None
    user = username_row.user
    if not include_deleted and user.deleted:
        return None
    return user


async def resolve_channel_query(query: str, *, channel_kind: str = "all") -> Channel | None:
    text = query.strip().lstrip("@")
    if not text:
        return None

    def _kind_ok(channel: Channel) -> bool:
        if channel_kind == "channel":
            return channel.channel
        if channel_kind == "supergroup":
            return not channel.channel
        return True

    if _ID_RE.match(text):
        channel_id = Channel.norm_id(int(text)) if int(text) > 1_000_000_000 else int(text)
        channel = await Channel.get_or_none(id=channel_id, deleted=False)
        return channel if channel is not None and _kind_ok(channel) else None

    username_row = await Username.get_or_none(username__iexact=text, channel_id__isnull=False).select_related(
        "channel",
    )
    if username_row is None or username_row.channel_id is None:
        return None
    channel = username_row.channel
    if channel.deleted or not _kind_ok(channel):
        return None
    return channel


async def resolve_chat_query(query: str) -> Chat | None:
    text = query.strip()
    if not text:
        return None

    if _ID_RE.match(text):
        chat_id = Chat.norm_id(int(text)) if int(text) > 1_000_000_000 else int(text)
        return await Chat.get_or_none(id=chat_id, deleted=False, migrated=False)

    if text.isdigit():
        return await Chat.get_or_none(id=int(text), deleted=False, migrated=False)
    return None


async def resolve_bot_query(query: str, *, include_system: bool = False) -> User | None:
    text = query.strip().lstrip("@")
    if not text:
        return None

    def _bot_ok(user: User | None) -> User | None:
        if user is None or not user.bot or user.deleted:
            return None
        if not include_system and user.system:
            return None
        return user

    if _ID_RE.match(text):
        return _bot_ok(await User.get_or_none(id=int(text), bot=True, deleted=False))

    username_row = await Username.get_or_none(username__iexact=text).select_related("user")
    if username_row is None or username_row.user_id is None:
        return None
    return _bot_ok(username_row.user)


async def search_users_substring(
        query: str, *, limit: int = 20, include_deleted: bool = False, include_system: bool = True,
) -> list[User]:
    text = query.strip().lstrip("@")
    if not text:
        return []

    base = User.all() if include_deleted else User.filter(deleted=False)
    base = base.filter(bot=False)
    if not include_system:
        base = base.filter(system=False)

    if _ID_RE.match(text):
        user = await base.get_or_none(id=int(text))
        return [user] if user is not None else []

    if _PHONE_RE.match(text):
        user = await base.get_or_none(phone_number=_normalize_phone(text))
        return [user] if user is not None else []

    user_ids = set(
        await Username.filter(username__icontains=text, user_id__isnull=False).values_list("user_id", flat=True)
    )
    if text:
        for user in await base.filter(first_name__icontains=text).limit(limit):
            user_ids.add(user.id)

    if not user_ids:
        return []
    return list(await base.filter(id__in=list(user_ids)).order_by("-id").limit(limit))