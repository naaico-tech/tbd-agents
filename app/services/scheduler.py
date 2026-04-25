"""RedBeat schedule management helpers.

Each ScheduledAgent document maps 1-to-1 with a RedBeat scheduler entry in Redis.
These helpers keep the two in sync.

RedBeat (installed as ``celery-redbeat``) is used over vanilla Celery Beat because
it stores schedules in Redis, making them dynamic (creatable/deletable at runtime)
and persistent across container restarts without relying on a flat file.
"""

import logging
from datetime import timedelta

from celery.schedules import schedule as celery_schedule
from redbeat import RedBeatSchedulerEntry

from app.celery_app import celery

logger = logging.getLogger(__name__)

# RedBeat key prefix used when constructing entry keys
_REDBEAT_PREFIX = "redbeat"


def _build_key(scheduled_agent_id: str) -> str:
    """Deterministic RedBeat key for a ScheduledAgent document ID."""
    return f"{_REDBEAT_PREFIX}:scheduled_agent:{scheduled_agent_id}"


def _interval_timedelta(value: int, unit: str) -> timedelta:
    """Convert interval_value + interval_unit to a timedelta."""
    if unit == "minutes":
        return timedelta(minutes=value)
    if unit == "hours":
        return timedelta(hours=value)
    if unit == "days":
        return timedelta(days=value)
    raise ValueError(f"Unknown interval unit: {unit!r}")


def create_schedule(scheduled_agent) -> str:
    """Register a new RedBeat entry and return its key.

    Args:
        scheduled_agent: A ``ScheduledAgent`` document instance.

    Returns:
        The RedBeat key string that was registered.
    """
    key = _build_key(str(scheduled_agent.id))
    delta = _interval_timedelta(scheduled_agent.interval_value, scheduled_agent.interval_unit)

    entry = RedBeatSchedulerEntry(
        name=key,
        task="run_scheduled_agent",
        schedule=celery_schedule(run_every=delta),
        args=[str(scheduled_agent.id)],
        app=celery,
    )
    entry.save()
    logger.info(
        "RedBeat: created schedule %s (every %s %s)",
        key, scheduled_agent.interval_value, scheduled_agent.interval_unit,
    )
    return key


def update_schedule(scheduled_agent) -> str:
    """Delete the existing RedBeat entry and create a fresh one.

    Use this whenever interval, start_at, or end_at changes.

    Args:
        scheduled_agent: A ``ScheduledAgent`` document with updated fields.

    Returns:
        The (unchanged) RedBeat key.
    """
    delete_schedule(scheduled_agent)
    return create_schedule(scheduled_agent)


def delete_schedule(scheduled_agent) -> None:
    """Remove the RedBeat entry for this schedule from Redis.

    Safe to call even if the entry no longer exists (swallows KeyError).

    Args:
        scheduled_agent: A ``ScheduledAgent`` document instance.
    """
    key = scheduled_agent.redbeat_key or _build_key(str(scheduled_agent.id))
    try:
        entry = RedBeatSchedulerEntry.from_key(key, app=celery)
        entry.delete()
        logger.info("RedBeat: deleted schedule %s", key)
    except KeyError:
        logger.debug("RedBeat: entry %s not found — already deleted or never created", key)
    except Exception:
        logger.exception("RedBeat: error deleting schedule %s", key)


def enable_schedule(scheduled_agent) -> str:
    """Re-create the RedBeat entry for a previously disabled schedule.

    Args:
        scheduled_agent: A ``ScheduledAgent`` document instance.

    Returns:
        The RedBeat key.
    """
    return create_schedule(scheduled_agent)


def disable_schedule(scheduled_agent) -> None:
    """Remove the RedBeat entry without deleting the ScheduledAgent document.

    Args:
        scheduled_agent: A ``ScheduledAgent`` document instance.
    """
    delete_schedule(scheduled_agent)
