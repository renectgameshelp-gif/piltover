from __future__ import annotations

from enum import IntEnum
from unittest.mock import AsyncMock, MagicMock

import pytest

from piltover.app.bot_handlers.interaction_handler import (
    BotInteractionHandler,
    RegisterCommand,
    SimpleHandler,
)
from piltover.db.models.bot_state_base import BotUserStateBase


class _TestState(IntEnum):
    WAIT = 1


class _TestUserState(BotUserStateBase):
    class Meta:
        table = "test_bot_user_state"


@pytest.mark.asyncio
async def test_simple_handler_delete_state() -> None:
    state = MagicMock()
    state.delete = AsyncMock()
    state.update_state = AsyncMock()
    send = AsyncMock(return_value="msg")

    handler = SimpleHandler(
        set_state=None,
        text="done",
        entities=None,
        send_message=send,
        del_state=True,
    )
    await handler(MagicMock(), MagicMock(), state)

    state.delete.assert_awaited_once()
    state.update_state.assert_not_awaited()
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_simple_handler_set_state_without_delete() -> None:
    state = MagicMock()
    state.delete = AsyncMock()
    state.update_state = AsyncMock()

    handler = SimpleHandler(
        set_state=_TestState.WAIT,
        text=None,
        entities=None,
        send_message=None,
        del_state=False,
    )
    await handler(MagicMock(), MagicMock(), state)

    state.update_state.assert_awaited_once_with(_TestState.WAIT, None)
    state.delete.assert_not_awaited()


def test_fetch_state_sets_need_fetch_state() -> None:
    bot = BotInteractionHandler(None)
    reg = (
        bot.command("cmd")
        .fetch_state()
    )
    assert reg.need_fetch_state is True
    assert not hasattr(reg, "_fetch_state")


def test_register_command_clone_preserves_name() -> None:
    bot = BotInteractionHandler(None)
    reg = bot.command("mybot").fetch_state()
    cloned = reg._clone()
    assert isinstance(cloned, RegisterCommand)
    assert cloned.name == "mybot"
    assert cloned.need_fetch_state is True


def test_ok_rejects_do_and_respond_on_same_step() -> None:
    bot = BotInteractionHandler(None)
    send = AsyncMock()

    async def handler(_peer, _message, _state):
        return None

    reg = (
        bot.command("x")
        .set_send_message_func(send)
        .when(state=None)
        .do(handler)
        .respond("text")
    )
    with pytest.raises(ValueError, match="Cannot combine .do\\(handler\\) and .respond"):
        reg.ok()


def test_ok_rejects_otherwise_handler_and_respond() -> None:
    bot = BotInteractionHandler(None)
    send = AsyncMock()

    async def handler(_peer, _message, _state):
        return None

    reg = (
        bot.command("x")
        .set_send_message_func(send)
        .otherwise(handler)
        .respond("text")
    )
    with pytest.raises(ValueError, match="Cannot combine .otherwise\\(handler\\) and .respond"):
        reg.ok()