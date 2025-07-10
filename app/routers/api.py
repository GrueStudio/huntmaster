
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime, UTC
from typing import Optional, List
from pydantic import BaseModel

from database import get_db
from models import Bid, TimeSlot, Hunt, User, Spawn

router = APIRouter(prefix="/api")

# Pydantic models for API responses
class UserResponse(BaseModel):
    id: int
    username: str

    class Config:
        from_attributes = True

class BidResponse(BaseModel):
    id: int
    user_id: int
    spawn_id: int
    bid_points: int
    hunt_window_start: datetime
    hunt_window_end: datetime
    claim_time: int  # in seconds
    status: str = "active"  # will be set based on associated hunt/timeslot

    class Config:
        from_attributes = True

class TimeSlotResponse(BaseModel):
    id: int
    user_id: int
    spawn_id: int
    start_time: datetime
    end_time: datetime
    points_paid: int
    bid_id: Optional[int]

    class Config:
        from_attributes = True

class HuntResponse(BaseModel):
    id: int
    user_id: int
    spawn_id: int
    start_time: datetime
    end_time: datetime
    points_paid: int
    bid_id: Optional[int]

    class Config:
        from_attributes = True

class ScheduleResponse(BaseModel):
    bids: List[BidResponse]
    timeslots: List[TimeSlotResponse]
    hunts: List[HuntResponse]
    users: List[UserResponse]
    total_bids: int
    total_timeslots: int
    total_hunts: int
    page: int
    page_size: int

@router.get("/schedule", response_model=ScheduleResponse)
async def get_schedule(
    spawn_id: Optional[int] = Query(None, description="Filter by spawn ID"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    start_time: Optional[datetime] = Query(None, description="Filter bids/hunts starting after this time"),
    end_time: Optional[datetime] = Query(None, description="Filter bids/hunts ending before this time"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db)
):
    """
    Get schedule data with filtering and pagination.

    - spawn_id: Filter by specific spawn
    - user_id: Filter by specific user
    - start_time: Filter bids/hunts that start after this time
    - end_time: Filter bids/hunts that end before this time
    - TimeSlots are not filtered by time frame as they will be managed separately
    """

    # Build base queries
    bid_query = db.query(Bid)
    hunt_query = db.query(Hunt)
    timeslot_query = db.query(TimeSlot)

    # Apply filters
    if spawn_id:
        bid_query = bid_query.filter(Bid.spawn_id == spawn_id)
        hunt_query = hunt_query.filter(Hunt.spawn_id == spawn_id)
        timeslot_query = timeslot_query.filter(TimeSlot.spawn_id == spawn_id)

    if user_id:
        bid_query = bid_query.filter(Bid.user_id == user_id)
        hunt_query = hunt_query.filter(Hunt.user_id == user_id)
        timeslot_query = timeslot_query.filter(TimeSlot.user_id == user_id)

    # Apply time filters only to bids and hunts (not timeslots)
    if start_time:
        bid_query = bid_query.filter(Bid.hunt_window_start >= start_time)
        hunt_query = hunt_query.filter(Hunt.start_time >= start_time)

    if end_time:
        bid_query = bid_query.filter(Bid.hunt_window_end <= end_time)
        hunt_query = hunt_query.filter(Hunt.end_time <= end_time)

    # Get total counts before pagination
    total_bids = bid_query.count()
    total_hunts = hunt_query.count()
    total_timeslots = timeslot_query.count()

    # Apply pagination to bids (primary data)
    offset = (page - 1) * page_size
    bids = bid_query.offset(offset).limit(page_size).all()

    # Get all timeslots and hunts for the filtered spawns/users (no pagination for these)
    timeslots = timeslot_query.all()
    hunts = hunt_query.all()

    # Get all unique users involved
    user_ids = set()
    for bid in bids:
        user_ids.add(bid.user_id)
    for timeslot in timeslots:
        user_ids.add(timeslot.user_id)
    for hunt in hunts:
        user_ids.add(hunt.user_id)

    users = []
    if user_ids:
        users = db.query(User).filter(User.id.in_(user_ids)).all()

    # Convert bids to response format and determine status
    bid_responses = []
    for bid in bids:
        # Check if this bid has associated hunt or timeslot
        has_hunt = any(h.bid_id == bid.id for h in hunts)
        has_timeslot = any(ts.bid_id == bid.id for ts in timeslots)

        status = "active"
        if has_hunt:
            status = "successful"
        elif has_timeslot:
            status = "successful"

        bid_response = BidResponse(
            id=bid.id,
            user_id=bid.user_id,
            spawn_id=bid.spawn_id,
            bid_points=bid.bid_points,
            hunt_window_start=bid.hunt_window_start,
            hunt_window_end=bid.hunt_window_end,
            claim_time=int(bid.claim_time.total_seconds()),
            status=status
        )
        bid_responses.append(bid_response)

    # Convert timeslots to response format
    timeslot_responses = [
        TimeSlotResponse(
            id=ts.id,
            user_id=ts.user_id,
            spawn_id=ts.spawn_id,
            start_time=ts.start_time,
            end_time=ts.end_time,
            points_paid=ts.points_paid,
            bid_id=ts.bid_id
        )
        for ts in timeslots
    ]

    # Convert hunts to response format
    hunt_responses = [
        HuntResponse(
            id=h.id,
            user_id=h.user_id,
            spawn_id=h.spawn_id,
            start_time=h.start_time,
            end_time=h.end_time,
            points_paid=h.points_paid,
            bid_id=h.bid_id
        )
        for h in hunts
    ]

    # Convert users to response format
    user_responses = [
        UserResponse(id=u.id, username=u.username)
        for u in users
    ]

    return ScheduleResponse(
        bids=bid_responses,
        timeslots=timeslot_responses,
        hunts=hunt_responses,
        users=user_responses,
        total_bids=total_bids,
        total_timeslots=total_timeslots,
        total_hunts=total_hunts,
        page=page,
        page_size=page_size
    )

@router.get("/bids", response_model=List[BidResponse])
async def get_bids(
    spawn_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get filtered and paginated bids"""
    query = db.query(Bid)

    if spawn_id:
        query = query.filter(Bid.spawn_id == spawn_id)
    if user_id:
        query = query.filter(Bid.user_id == user_id)
    if start_time:
        query = query.filter(Bid.hunt_window_start >= start_time)
    if end_time:
        query = query.filter(Bid.hunt_window_end <= end_time)

    offset = (page - 1) * page_size
    bids = query.offset(offset).limit(page_size).all()

    return [
        BidResponse(
            id=bid.id,
            user_id=bid.user_id,
            spawn_id=bid.spawn_id,
            bid_points=bid.bid_points,
            hunt_window_start=bid.hunt_window_start,
            hunt_window_end=bid.hunt_window_end,
            claim_time=int(bid.claim_time.total_seconds()),
            status="active"
        )
        for bid in bids
    ]

@router.get("/timeslots", response_model=List[TimeSlotResponse])
async def get_timeslots(
    spawn_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get filtered and paginated timeslots (no time filtering)"""
    query = db.query(TimeSlot)

    if spawn_id:
        query = query.filter(TimeSlot.spawn_id == spawn_id)
    if user_id:
        query = query.filter(TimeSlot.user_id == user_id)

    offset = (page - 1) * page_size
    timeslots = query.offset(offset).limit(page_size).all()

    return [
        TimeSlotResponse(
            id=ts.id,
            user_id=ts.user_id,
            spawn_id=ts.spawn_id,
            start_time=ts.start_time,
            end_time=ts.end_time,
            points_paid=ts.points_paid,
            bid_id=ts.bid_id
        )
        for ts in timeslots
    ]

@router.get("/hunts", response_model=List[HuntResponse])
async def get_hunts(
    spawn_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get filtered and paginated hunts"""
    query = db.query(Hunt)

    if spawn_id:
        query = query.filter(Hunt.spawn_id == spawn_id)
    if user_id:
        query = query.filter(Hunt.user_id == user_id)
    if start_time:
        query = query.filter(Hunt.start_time >= start_time)
    if end_time:
        query = query.filter(Hunt.end_time <= end_time)

    offset = (page - 1) * page_size
    hunts = query.offset(offset).limit(page_size).all()

    return [
        HuntResponse(
            id=hunt.id,
            user_id=hunt.user_id,
            spawn_id=hunt.spawn_id,
            start_time=hunt.start_time,
            end_time=hunt.end_time,
            points_paid=hunt.points_paid,
            bid_id=hunt.bid_id
        )
        for hunt in hunts
    ]
