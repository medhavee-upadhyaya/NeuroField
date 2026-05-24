"""Replay API routes — query historical snapshots from SQLite."""
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

replay_router = APIRouter(prefix="/replay")

_logger = None


def inject_logger(logger):
    global _logger
    _logger = logger


@replay_router.get("/bounds")
async def get_bounds():
    """Min/max timestamps and total snapshot count in the DB."""
    if not _logger:
        raise HTTPException(503, "Logger not available")
    return _logger.get_bounds()


@replay_router.get("/timeline")
async def get_timeline(
    from_ts: float = Query(default=0),
    to_ts: Optional[float] = Query(default=None),
):
    """Compact timeline — one entry per snapshot with anomaly/critical counts."""
    if not _logger:
        raise HTTPException(503, "Logger not available")
    return {"timeline": _logger.get_timeline(from_ts, to_ts or time.time())}


@replay_router.get("/snapshot")
async def get_snapshot(ts: float = Query(...)):
    """Full snapshot closest to the given timestamp."""
    if not _logger:
        raise HTTPException(503, "Logger not available")
    snap = _logger.get_snapshot_at(ts)
    if not snap:
        raise HTTPException(404, "No snapshots found")
    return snap


@replay_router.get("/range")
async def get_range(
    from_ts: float = Query(...),
    to_ts: float = Query(...),
    limit: int = Query(default=100, le=500),
):
    """All snapshots between from_ts and to_ts (for bulk playback)."""
    if not _logger:
        raise HTTPException(503, "Logger not available")
    snaps = _logger.get_snapshots_range(from_ts, to_ts, limit)
    return {"snapshots": snaps, "count": len(snaps)}


@replay_router.get("/events")
async def get_events(
    from_ts: float = Query(default=0),
    to_ts: Optional[float] = Query(default=None),
):
    """Agent action events within the time range."""
    if not _logger:
        raise HTTPException(503, "Logger not available")
    return {"events": _logger.get_events(from_ts, to_ts or time.time())}
