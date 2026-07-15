import warnings
from time import time

import piltover.app.utils.updates_manager as upd
from piltover.app.utils.updates_manager import UpdatesWithDefaults
from piltover.db.enums import PeerType
from piltover.db.models import User, Peer, MessageRef
from piltover.session import SessionManager
from piltover.tl import UpdateServiceNotification, MessageMediaEmpty, objects
from piltover.tl.base import ReplyMarkup


async def send_official_notification_message(
        user_id: int, text: str, entities: list | None, *, reply_markup: ReplyMarkup | None = None,
) -> bool:
    system_user = await User.get_or_none(id=777000, system=True).only("id")
    if system_user is None:
        warnings.warn(
            "System notifications user (id 777000) does not exist. "
            "Some features (related to system notifications) won't be available."
        )
        return False

    peer_system, created = await Peer.get_or_create(
        owner_id=user_id, user=system_user, defaults={"type": PeerType.USER}
    )
    if not created:
        peer_system.user = system_user

    message = await MessageRef.create_for_peer(
        peer_system, system_user, opposite=False, unhide_dialog=True,
        message=text, entities=entities,
        reply_markup=reply_markup.write() if reply_markup is not None else None,
    )

    await upd.send_message(user_id, message, False)

    return True


async def broadcast_official_notification_message(
        text: str, entities: list | None, *, reply_markup: ReplyMarkup | None = None,
) -> int:
    system_user = await User.get_or_none(id=777000, system=True).only("id")
    if system_user is None:
        warnings.warn(
            "System notifications user (id 777000) does not exist. "
            "Some features (related to system notifications) won't be available."
        )
        return 0

    user_ids = await User.filter(deleted=False, bot=False).values_list("id", flat=True)
    sent = 0
    for user_id in user_ids:
        if await send_official_notification_message(
                user_id, text, entities, reply_markup=reply_markup,
        ):
            sent += 1
    return sent


async def broadcast_service_notification(
        text: str, entities: list | None, *, popup: bool = True,
) -> int:
    user_ids = await User.filter(deleted=False, bot=False).values_list("id", flat=True)
    sent = 0
    for user_id in user_ids:
        if await send_service_notification(user_id, text, entities, popup=popup):
            sent += 1
    return sent


async def send_service_notification(
        user_id: int, text: str, entities: list | None, *, popup: bool = True,
) -> bool:
    tl_entities = []
    if entities:
        for entity in entities:
            entity_copy = dict(entity)
            tl_id = entity_copy.pop("_")
            tl_entities.append(objects[tl_id](**entity_copy))

    await SessionManager.send(
        UpdatesWithDefaults(updates=[
            UpdateServiceNotification(
                popup=popup,
                inbox_date=int(time()) if popup else None,
                type_=f"PILTOVER_{int(time())}",
                message=text,
                media=MessageMediaEmpty(),
                entities=tl_entities,
            ),
        ]),
        user_id,
    )
    return True
