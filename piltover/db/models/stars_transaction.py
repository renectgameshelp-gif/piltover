from __future__ import annotations

from uuid import uuid4

from tortoise import Model, fields

from piltover.db import models
from piltover.db.enums import StarsTransactionPeerType
from piltover.tl import (
    StarsAmount, StarsTransaction as TLStarsTransaction, StarsTransactionPeer,
    StarsTransactionPeerFragment, StarsTransactionPeerAppStore, StarsTransactionPeerPlayMarket,
    StarsTransactionPeerPremiumBot, StarsTransactionPeerAds, StarsTransactionPeerAPI, PeerUser,
)
from piltover.utils.users_chats_channels import UsersChatsChannels


class StarsTransaction(Model):
    transaction_id: str = fields.CharField(max_length=64, primary_key=True)
    user: models.User = fields.ForeignKeyField("models.User", related_name="stars_transactions")
    stars_amount: int = fields.BigIntField()
    stars_nanos: int = fields.IntField(default=0)
    inbound: bool = fields.BooleanField()
    date: int = fields.IntField()
    peer_type: StarsTransactionPeerType = fields.IntEnumField(StarsTransactionPeerType)
    peer_user: models.User | None = fields.ForeignKeyField(
        "models.User", null=True, default=None, related_name="stars_transactions_as_peer",
    )
    title: str | None = fields.CharField(max_length=256, null=True, default=None)
    description: str | None = fields.CharField(max_length=512, null=True, default=None)
    gift: bool = fields.BooleanField(default=False)
    refund: bool = fields.BooleanField(default=False)

    user_id: int
    peer_user_id: int | None

    @staticmethod
    def gen_id() -> str:
        return uuid4().hex

    def to_stars_amount(self) -> StarsAmount:
        signed_amount = self.stars_amount if self.inbound else -self.stars_amount
        signed_nanos = self.stars_nanos if self.inbound else -self.stars_nanos
        return StarsAmount(amount=signed_amount, nanos=signed_nanos)

    def _peer_tl(self, ucc: UsersChatsChannels) -> StarsTransactionPeer | StarsTransactionPeerFragment | StarsTransactionPeerAppStore | StarsTransactionPeerPlayMarket | StarsTransactionPeerPremiumBot | StarsTransactionPeerAds | StarsTransactionPeerAPI:
        match self.peer_type:
            case StarsTransactionPeerType.FRAGMENT:
                return StarsTransactionPeerFragment()
            case StarsTransactionPeerType.APP_STORE:
                return StarsTransactionPeerAppStore()
            case StarsTransactionPeerType.PLAY_MARKET:
                return StarsTransactionPeerPlayMarket()
            case StarsTransactionPeerType.PREMIUM_BOT:
                return StarsTransactionPeerPremiumBot()
            case StarsTransactionPeerType.ADS:
                return StarsTransactionPeerAds()
            case StarsTransactionPeerType.API:
                return StarsTransactionPeerAPI()
            case StarsTransactionPeerType.PEER:
                if self.peer_user_id is not None:
                    ucc.add_user(self.peer_user_id)
                return StarsTransactionPeer(peer=PeerUser(user_id=self.peer_user_id or 0))
        return StarsTransactionPeerFragment()

    def to_tl(self, ucc: UsersChatsChannels) -> TLStarsTransaction:
        return TLStarsTransaction(
            id=self.transaction_id,
            stars=self.to_stars_amount(),
            date=self.date,
            peer=self._peer_tl(ucc),
            title=self.title,
            description=self.description,
            gift=self.gift,
            refund=self.refund,
        )