from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from time import time
from typing import Any

from loguru import logger

from piltover.app.utils.bot_api.serialize import message_to_bot_api
from piltover.db.models import MessageRef, Peer, User


@dataclass
class _BotWebhookState:
    url: str = ""
    has_custom_certificate: bool = False
    pending_update_count: int = 0
    ip_address: str | None = None
    last_error_date: int | None = None
    last_error_message: str | None = None
    max_connections: int | None = None
    allowed_updates: list[str] | None = None


@dataclass
class _BotUpdatesState:
    updates: list[dict[str, Any]] = field(default_factory=list)
    next_update_id: int = 1
    waiters: list[asyncio.Event] = field(default_factory=list)
    webhook: _BotWebhookState = field(default_factory=_BotWebhookState)


class BotApiUpdatesStore:
    MAX_UPDATES_PER_BOT = 10_000
    MAX_UPDATE_AGE_SECONDS = 24 * 60 * 60

    def __init__(self) -> None:
        self._bots: dict[int, _BotUpdatesState] = {}

    def _state(self, bot_id: int) -> _BotUpdatesState:
        if bot_id not in self._bots:
            self._bots[bot_id] = _BotUpdatesState()
        return self._bots[bot_id]

    def has_webhook(self, bot_id: int) -> bool:
        return bool(self._state(bot_id).webhook.url)

    def get_webhook_info(self, bot_id: int) -> dict[str, Any]:
        webhook = self._state(bot_id).webhook
        state = self._state(bot_id)
        result: dict[str, Any] = {
            "url": webhook.url,
            "has_custom_certificate": webhook.has_custom_certificate,
            "pending_update_count": len(state.updates),
        }
        if webhook.ip_address:
            result["ip_address"] = webhook.ip_address
        if webhook.last_error_date is not None:
            result["last_error_date"] = webhook.last_error_date
        if webhook.last_error_message:
            result["last_error_message"] = webhook.last_error_message
        if webhook.max_connections is not None:
            result["max_connections"] = webhook.max_connections
        if webhook.allowed_updates is not None:
            result["allowed_updates"] = webhook.allowed_updates
        return result

    def set_webhook(
            self, bot_id: int, url: str, *, drop_pending_updates: bool = False,
            allowed_updates: list[str] | None = None, max_connections: int | None = None,
            ip_address: str | None = None,
    ) -> None:
        state = self._state(bot_id)
        state.webhook.url = url
        state.webhook.allowed_updates = allowed_updates
        state.webhook.max_connections = max_connections
        state.webhook.ip_address = ip_address
        if drop_pending_updates:
            state.updates.clear()
            state.webhook.pending_update_count = 0

    def delete_webhook(self, bot_id: int, *, drop_pending_updates: bool = False) -> None:
        state = self._state(bot_id)
        state.webhook = _BotWebhookState()
        if drop_pending_updates:
            state.updates.clear()

    def _prune_old_updates(self, state: _BotUpdatesState) -> None:
        now = int(time())
        state.updates = [
            update for update in state.updates
            if now - update.get("_created_at", now) < self.MAX_UPDATE_AGE_SECONDS
        ]
        if len(state.updates) > self.MAX_UPDATES_PER_BOT:
            state.updates = state.updates[-self.MAX_UPDATES_PER_BOT:]

    def _notify_waiters(self, state: _BotUpdatesState) -> None:
        waiters = state.waiters
        state.waiters = []
        for event in waiters:
            event.set()

    async def enqueue_incoming_message(self, bot_user: User, peer: Peer, message: MessageRef) -> None:
        state = self._state(bot_user.id)
        update = {
            "update_id": state.next_update_id,
            "message": await message_to_bot_api(bot_user, peer, message),
            "_created_at": int(time()),
        }
        state.next_update_id += 1
        self._prune_old_updates(state)

        if state.webhook.url:
            state.webhook.pending_update_count = len(state.updates) + 1
            logger.debug("Bot API webhook delivery is not implemented yet for bot {}", bot_user.id)
            return

        state.updates.append(update)
        self._notify_waiters(state)

    async def get_updates(
            self, bot_id: int, *, offset: int | None = None, limit: int = 100, timeout: int = 0,
    ) -> list[dict[str, Any]]:
        if self.has_webhook(bot_id):
            raise _BotApiConflict("can't use getUpdates while webhook is active")

        state = self._state(bot_id)
        limit = max(1, min(limit, 100))

        if offset is not None:
            if offset < 0:
                count = min(-offset, len(state.updates))
                pending = state.updates[-count:] if count else []
                state.updates.clear()
                return [{k: v for k, v in update.items() if k != "_created_at"} for update in pending]

            state.updates = [update for update in state.updates if update["update_id"] >= offset]

        if not state.updates and timeout > 0:
            event = asyncio.Event()
            state.waiters.append(event)
            try:
                await asyncio.wait_for(event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass
            finally:
                if event in state.waiters:
                    state.waiters.remove(event)

        pending = state.updates[:limit]
        state.updates = state.updates[limit:]
        return [{k: v for k, v in update.items() if k != "_created_at"} for update in pending]


class _BotApiConflict(Exception):
    pass


bot_api_updates = BotApiUpdatesStore()