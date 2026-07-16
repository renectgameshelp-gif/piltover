from __future__ import annotations

from datetime import datetime, UTC

from tortoise import Model, fields

from piltover.db import models
from piltover.tl import (
    GroupCallParticipant as TLGroupCallParticipant,
    GroupCallParticipantVideo,
    GroupCallParticipantVideoSourceGroup,
    PeerUser,
    PeerChannel,
)

DEFAULT_GROUP_CALL_VOLUME = 10000
ADMIN_VOLUME_MUTE_THRESHOLD = 100


class GroupCallParticipant(Model):
    id: int = fields.BigIntField(primary_key=True)
    group_call: models.GroupCall = fields.ForeignKeyField("models.GroupCall", related_name="participants")
    user: models.User = fields.ForeignKeyField("models.User", related_name="group_call_participations")
    join_as_user: models.User | None = fields.ForeignKeyField(
        "models.User", null=True, default=None, related_name="group_call_join_as_participations",
    )
    join_as_channel: models.Channel | None = fields.ForeignKeyField(
        "models.Channel", null=True, default=None, related_name="group_call_join_as_participations",
    )
    source: int = fields.IntField()
    muted: bool = fields.BooleanField(default=False)
    muted_by_admin: bool = fields.BooleanField(default=False)
    volume: int = fields.IntField(default=10000)
    volume_by_admin: bool = fields.BooleanField(default=False)
    video_stopped: bool = fields.BooleanField(default=True)
    video_source: int | None = fields.IntField(null=True, default=None)
    presentation_source: int | None = fields.IntField(null=True, default=None)
    video_endpoint: str | None = fields.CharField(max_length=256, null=True, default=None)
    presentation_endpoint: str | None = fields.CharField(max_length=256, null=True, default=None)
    video_source_groups: list[dict] | None = fields.JSONField(null=True, default=None)
    presentation_source_groups: list[dict] | None = fields.JSONField(null=True, default=None)
    video_paused: bool = fields.BooleanField(default=False)
    presentation_paused: bool = fields.BooleanField(default=False)
    raise_hand_rating: int | None = fields.BigIntField(null=True, default=None)
    left: bool = fields.BooleanField(default=False)
    joined_at: datetime = fields.DatetimeField(auto_now_add=True)

    group_call_id: int
    user_id: int
    join_as_user_id: int | None
    join_as_channel_id: int | None

    class Meta:
        unique_together = (
            ("group_call", "user"),
            ("group_call", "source"),
        )

    def is_admin_volume_silent(self) -> bool:
        return self.volume_by_admin and self.volume <= ADMIN_VOLUME_MUTE_THRESHOLD

    def is_admin_muted(self) -> bool:
        return self.muted_by_admin or self.is_admin_volume_silent()

    def can_self_unmute_participant(self) -> bool:
        if self.is_admin_muted():
            return False
        return True

    def format_mute_debug(self, *, self_user_id: int | None = None, versioned: bool | None = None) -> str:
        tl = self.to_tl(self_user_id=self_user_id, min_=False, versioned=versioned)
        peer = self.to_tl_peer()
        peer_label = (
            f"channel={peer.channel_id}"
            if isinstance(peer, PeerChannel)
            else f"user={peer.user_id}"
        )
        return (
            f"participant_user={self.user_id} {peer_label} source={self.source} "
            f"db(muted={self.muted} muted_by_admin={self.muted_by_admin} "
            f"volume={self.volume} volume_by_admin={self.volume_by_admin} "
            f"admin_muted={self.is_admin_muted()}) "
            f"tl(muted={tl.muted} can_self_unmute={tl.can_self_unmute} "
            f"muted_by_you={tl.muted_by_you} volume_by_admin={tl.volume_by_admin} volume={tl.volume} "
            f"versioned={tl.versioned} min={tl.min} is_self={tl.is_self})"
        )

    def to_tl_peer(self) -> PeerUser | PeerChannel:
        if self.join_as_channel_id is not None:
            return PeerChannel(channel_id=models.Channel.make_id_from(self.join_as_channel_id))
        user_id = self.join_as_user_id or self.user_id
        return PeerUser(user_id=user_id)

    @staticmethod
    def _source_groups_to_tl(
            source_groups: list[dict] | None,
    ) -> list[GroupCallParticipantVideoSourceGroup]:
        if not source_groups:
            return []
        result: list[GroupCallParticipantVideoSourceGroup] = []
        for group in source_groups:
            if not isinstance(group, dict):
                continue
            sources = group.get("sources")
            if not isinstance(sources, list):
                continue
            result.append(GroupCallParticipantVideoSourceGroup(
                semantics=str(group.get("semantics", "default")),
                sources=[int(s) for s in sources],
            ))
        return result

    def _video_stream_to_tl(
            self,
            *,
            source: int | None,
            endpoint: str | None,
            source_groups: list[dict] | None,
            paused: bool,
    ) -> GroupCallParticipantVideo | None:
        if source is None or not endpoint:
            return None
        groups = self._source_groups_to_tl(source_groups)
        if not groups:
            groups = [GroupCallParticipantVideoSourceGroup(semantics="default", sources=[source])]
        return GroupCallParticipantVideo(
            endpoint=endpoint,
            source_groups=groups,
            paused=paused,
            audio_source=self.source,
        )

    def to_tl_active_ping(self) -> TLGroupCallParticipant:
        now = int(datetime.now(UTC).timestamp())
        return TLGroupCallParticipant(
            min=True,
            versioned=False,
            video_joined=not self.video_stopped,
            peer=self.to_tl_peer(),
            date=int(self.joined_at.timestamp()),
            active_date=now,
            source=self.source,
        )

    def to_tl(
            self,
            *,
            self_user_id: int | None = None,
            just_joined: bool = False,
            min_: bool = False,
            versioned: bool | None = None,
    ) -> TLGroupCallParticipant:
        now = int(datetime.now(UTC).timestamp())
        # Admin mute uses muted + !can_self_unmute (person icon). volume_by_admin is only for
        # partial volume — silent admin volume (0%) must not be sent as volume_by_admin or
        # clients show a 0% slider instead of the admin-mute icon.
        admin_muted = self.is_admin_muted()
        show_volume_override = self.volume_by_admin and not admin_muted
        is_self = self_user_id is not None and self.user_id == self_user_id
        if versioned is None:
            versioned = not min_
        # muted_by_you is for per-viewer local mute ("muted for you"), not admin mute.
        video = self._video_stream_to_tl(
            source=self.video_source,
            endpoint=self.video_endpoint,
            source_groups=self.video_source_groups,
            paused=self.video_paused,
        )
        presentation = self._video_stream_to_tl(
            source=self.presentation_source,
            endpoint=self.presentation_endpoint,
            source_groups=self.presentation_source_groups,
            paused=self.presentation_paused,
        )
        return TLGroupCallParticipant(
            muted=self.muted or admin_muted,
            left=self.left,
            can_self_unmute=self.can_self_unmute_participant(),
            volume_by_admin=show_volume_override,
            versioned=versioned,
            min=min_,
            just_joined=just_joined,
            is_self=is_self,
            video_joined=not self.video_stopped,
            peer=self.to_tl_peer(),
            date=int(self.joined_at.timestamp()),
            active_date=now,
            source=self.source,
            volume=self.volume if show_volume_override else None,
            raise_hand_rating=self.raise_hand_rating,
            video=video,
            presentation=presentation,
        )