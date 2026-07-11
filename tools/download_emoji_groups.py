import argparse
import json
import shutil
from array import array
from asyncio import get_event_loop
from pathlib import Path
from typing import Any

from loguru import logger
from pyrogram import Client

from download_utils import DEFAULT_SESSION_BY_SCRIPT, DownloadClientArgs, add_download_client_args, download_client
from tests._emoji_groups_compat import (
    EmojiGroupCompat,
    EmojiGroupGreetingCompat,
    EmojiGroupPremiumCompat,
    EmojiGroupsCompat,
    GetEmojiGroupsCompat,
    GetEmojiProfilePhotoGroupsCompat,
    GetEmojiStatusGroupsCompat,
    GetEmojiStickerGroupsCompat,
)

GROUPS = [
    ("sticker_groups", GetEmojiStickerGroupsCompat(hash=0)),
    ("groups", GetEmojiGroupsCompat(hash=0)),
    ("status_groups", GetEmojiStatusGroupsCompat(hash=0)),
    ("profile_photo_groups", GetEmojiProfilePhotoGroupsCompat(hash=0)),
]

COMPAT_CLASSES = (
    GetEmojiStickerGroupsCompat,
    GetEmojiGroupsCompat,
    GetEmojiStatusGroupsCompat,
    GetEmojiProfilePhotoGroupsCompat,
    EmojiGroupsCompat,
    EmojiGroupCompat,
    EmojiGroupGreetingCompat,
    EmojiGroupPremiumCompat,
)


def tl_object_default(obj: Any) -> str | dict[str, str] | list:
    if isinstance(obj, bytes):
        return repr(obj)
    if isinstance(obj, array):
        return list(obj)

    return {
        "_": obj.QUALNAME,
        **{
            attr: getattr(obj, attr)
            for attr in obj.__slots__
            if getattr(obj, attr) is not None
        },
    }


async def extract_emoji_groups(client: Client, out_dir: Path) -> None:
    from pyrogram.raw import all as pyrogram_all
    from piltover.tl import all as piltover_all

    for cls in COMPAT_CLASSES:
        pyrogram_all.objects[cls.tlid()] = piltover_all.objects[cls.tlid()] = cls

    try:
        for name, req in GROUPS:
            result = await client.invoke(req)
            if not hasattr(result, "groups"):
                logger.error(
                    "Invalid response for emoji group {name!r}: {type}",
                    name=name,
                    type=getattr(result, "QUALNAME", type(result).__name__),
                )
                continue

            logger.success(f"Got {len(result.groups)} emoji groups for {name!r}")
            with open(out_dir / f"{name}.json", "w") as f:
                json.dump(result, f, indent=4, default=tl_object_default, ensure_ascii=False)
    finally:
        for cls in COMPAT_CLASSES:
            piltover_all.objects[cls.tlid()] = cls.RESTORE_CLS


async def main() -> None:
    parser = argparse.ArgumentParser()
    add_download_client_args(parser, default_session=DEFAULT_SESSION_BY_SCRIPT["emoji_groups"])
    args = parser.parse_args(namespace=DownloadClientArgs())

    out_dir = args.data_dir / "emoji_groups"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / ".gitignore", "w") as f:
        f.write("*\n")

    async with download_client(args) as client:
        await extract_emoji_groups(client, out_dir)


if __name__ == "__main__":
    get_event_loop().run_until_complete(main())