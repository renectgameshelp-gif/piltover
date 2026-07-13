from datetime import datetime, timedelta, UTC

from tortoise.transactions import in_transaction

from piltover.context import request_ctx
from piltover.db.models import BotPrecheckoutQuery
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.tl.functions.messages import SetBotPrecheckoutResults
from piltover.worker import MessageHandler

handler = MessageHandler("messages.bot_payments")


@handler.on_request(SetBotPrecheckoutResults, ReqHandlerFlags.USER_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def set_bot_precheckout_results(request: SetBotPrecheckoutResults, user_id: int) -> bool:
    ctx = request_ctx.get()

    async with in_transaction():
        query = await BotPrecheckoutQuery.select_for_update(no_key=True).get_or_none(
            bot_id=user_id,
            id=request.query_id,
            created_at__gte=datetime.now(UTC) - timedelta(seconds=15),
        )
        if query is None:
            raise ErrorRpc(error_code=400, error_message="QUERY_ID_INVALID")

        if request.success:
            data = b"1"
        else:
            data = (request.error or "PAYMENT_FAILED").encode("utf-8")

        await ctx.worker.pubsub.notify(topic=f"bot-precheckout-query/{query.id}", data=data)

    return True