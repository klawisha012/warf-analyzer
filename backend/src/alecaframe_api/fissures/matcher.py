"""Pure predicate: does a live fissure satisfy a subscription filter?

A `None` field on the subscription means "any" for that axis. A fissure
matches iff every *specified* (non-None) axis is equal."""
from __future__ import annotations

from alecaframe_api.fissures.models import Fissure, Subscription


def matches(fissure: Fissure, sub: Subscription) -> bool:
    if sub.era is not None and fissure.era != sub.era:
        return False
    if sub.mission_type is not None and fissure.mission_type != sub.mission_type:
        return False
    if sub.is_hard is not None and fissure.is_hard != sub.is_hard:
        return False
    if sub.is_storm is not None and fissure.is_storm != sub.is_storm:
        return False
    return True
