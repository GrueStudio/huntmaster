# /app/routers/scheduling.py

from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta, UTC
from typing import Annotated # For FastAPI dependency injection with Form/Body

from database import get_db
from models import World, Character, Spawn, SpawnChangeProposal, ProposalStatus, User, Points, Bid # Import Points and Bid models
from templating import templates

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/worlds/{world_name}/spawns/{spawn_name}/bid", response_class=HTMLResponse)
async def get_bid_form(
    request: Request,
    world_name: str,
    spawn_name: str,
    db: Session = Depends(get_db)
):
    """
    Displays the form for placing a bid on a specific spawn.
    It fetches spawn details, relevant bid constraints (from spawn or active temporary proposals),
    and the user's current points for that spawn.
    """
    user_id = request.session.get('user_id')
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        request.session.pop('user_id', None)
        request.session.pop('username', None)
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # 1. Find the world (case-insensitive)
    world = db.query(World).filter(func.lower(World.name) == world_name.lower()).first()
    if not world:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="World not found")

    # 2. Find the spawn within that world (case-insensitive)
    spawn = db.query(Spawn).filter(
        func.lower(Spawn.name) == spawn_name.lower(),
        Spawn.world_id == world.id
    ).first()
    if not spawn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Spawn not found in this world")

    # 3. Determine bid settings: Check for active temporary change proposal
    now_utc = datetime.now(UTC)
    active_temp_proposal = db.query(SpawnChangeProposal).filter(
        SpawnChangeProposal.spawn_id == spawn.id,
        SpawnChangeProposal.status == ProposalStatus.APPROVED,
        SpawnChangeProposal.start_time.isnot(None), # Must be a temporary change
        SpawnChangeProposal.end_time.isnot(None),   # Must be a temporary change
        SpawnChangeProposal.start_time <= now_utc,
        SpawnChangeProposal.end_time >= now_utc
    ).order_by(SpawnChangeProposal.approved_at.desc()).first()

    bid_settings = {}
    if active_temp_proposal:
        # Use settings from the active temporary proposal
        bid_settings['min_claim_duration_minutes'] = int(active_temp_proposal.claim_time_min.total_seconds() // 60)
        bid_settings['max_claim_duration_minutes'] = int(active_temp_proposal.claim_time_max.total_seconds() // 60)
        logger.info(f"Using temporary proposal settings for {spawn.name}: Min={bid_settings['min_claim_duration_minutes']}m, Max={bid_settings['max_claim_duration_minutes']}m")
    else:
        # Use settings from the Spawn itself
        bid_settings['min_claim_duration_minutes'] = int(spawn.claim_time_min.total_seconds() // 60)
        bid_settings['max_claim_duration_minutes'] = int(spawn.claim_time_max.total_seconds() // 60)
        logger.info(f"Using default spawn settings for {spawn.name}: Min={bid_settings['min_claim_duration_minutes']}m, Max={bid_settings['max_claim_duration_minutes']}m")

    # 4. Fetch user's spawn-specific points
    user_spawn_points_entry = db.query(Points).filter(
        Points.user_id == user.id,
        Points.spawn_id == spawn.id
    ).first()

    current_points_for_spawn = 0.0
    if user_spawn_points_entry:
        current_points_for_spawn = float(user_spawn_points_entry.points) # Ensure float for JS
    else:
        # "First Bid Attempt" strategy: Assume starting points if no entry exists.
        # The actual DB insertion will happen on the POST endpoint.
        current_points_for_spawn = 1000.00 # As per your requirement

    # Prepare breadcrumbs for the template
    breadcrumbs = [
        { 'text': 'Dashboard', 'link': '/dashboard' },
        { 'text': 'Worlds', 'link': '/worlds' },
        { 'text': world.name, 'link': f'/worlds/{world.name}' },
        { 'text': spawn.name, 'link': f'/worlds/{world.name}/spawns/{spawn.name}' },
        { 'text': 'Place Bid', 'link': None }
    ]

    return templates.TemplateResponse(
        "bid_placement_form.html", # Assuming your HTML is named this
        {
            "request": request,
            "current_user": user, # Pass the user object for layout macro
            "world": world,       # Pass the full world object
            "spawn": spawn,       # Pass the full spawn object
            "bid_settings": bid_settings, # Min/max claim duration
            "current_points_for_spawn": current_points_for_spawn, # Current points for this spawn
            "breadcrumbs": breadcrumbs
        }
    )

@router.post("/worlds/{world_name}/spawns/{spawn_name}/bid", response_class=JSONResponse)
async def post_bid(
    request: Request,
    world_name: str,
    spawn_name: str,
    spawn_id: Annotated[int, Form(...)], # Changed to Form for direct access from request body
    hunt_window_start: Annotated[str, Form(...)], # ISO string
    hunt_window_end: Annotated[str, Form(...)],   # ISO string
    preferred_hunt_duration_minutes: Annotated[int, Form(...)],
    bid_points: Annotated[int, Form(...)],
    db: Session = Depends(get_db)
):
    """
    Handles the submission of a new bid for a spawn.
    Implements the "First Bid Attempt" point assignment and point deduction.
    """
    user_id = request.session.get('user_id')
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        request.session.pop('user_id', None)
        request.session.pop('username', None)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You must be logged in to place a bid.")

    # Validate world and spawn exist
    world = db.query(World).filter(func.lower(World.name) == world_name.lower()).first()
    if not world:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="World not found")

    spawn = db.query(Spawn).filter(
        func.lower(Spawn.name) == spawn_name.lower(),
        Spawn.world_id == world.id,
        Spawn.id == spawn_id # Ensure spawn_id matches for robustness
    ).first()
    if not spawn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Spawn not found in this world.")

    # Parse datetime strings to UTC datetime objects
    try:
        parsed_hunt_window_start = datetime.fromisoformat(hunt_window_start.replace('Z', '+00:00'))
        parsed_hunt_window_end = datetime.fromisoformat(hunt_window_end.replace('Z', '+00:00'))
        # Ensure they are UTC aware
        if parsed_hunt_window_start.tzinfo is None:
            parsed_hunt_window_start = parsed_hunt_window_start.replace(tzinfo=UTC)
        if parsed_hunt_window_end.tzinfo is None:
            parsed_hunt_window_end = parsed_hunt_window_end.replace(tzinfo=UTC)

    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date/time format for hunt window.")

    # Basic validation for bid points and time window
    if bid_points <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bid points must be positive.")
    if parsed_hunt_window_start >= parsed_hunt_window_end:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Hunt window end time must be after start time.")
    if parsed_hunt_window_start < datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Hunt window must be in the future.")

    # 1. Get or Create User's Spawn-Specific Points
    user_points_entry = db.query(Points).filter(
        Points.user_id == user.id,
        Points.spawn_id == spawn.id
    ).first()

    if not user_points_entry:
        # First Bid Attempt: Assign initial points
        user_points_entry = Points(
            user_id=user.id,
            spawn_id=spawn.id,
            points=1000.00 # Initial points as per requirement
        )
        db.add(user_points_entry)
        db.flush() # Flush to make the new entry available for point deduction
        logger.info(f"Assigned initial 1000 points to user {user.id} for spawn {spawn.name}.")

    # 2. Check if user has enough points
    if user_points_entry.points < bid_points:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Insufficient points for this bid. You have {user_points_entry.points} points.")

    # Also enforce minimum bid (1/4 of total points)
    min_bid_required = user_points_entry.points / 4
    if bid_points < min_bid_required:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"You must bid at least {min_bid_required:.0f} points (1/4 of your total).")


    # 3. Deduct points
    user_points_entry.points -= bid_points
    db.add(user_points_entry) # Mark for update

    # 4. Create the Bid entry
    new_bid = Bid(
        user_id=user.id, # Use user_id directly
        spawn_id=spawn.id,
        bid_points=bid_points,
        hunt_window_start=parsed_hunt_window_start,
        hunt_window_end=parsed_hunt_window_end,
        # claim_time_offset: This will be determined by the scheduler or default to 0 for now
        # For Sprint 0.5.0, we can set a default or leave it nullable if not used immediately by scheduler
        # Assuming preferred_hunt_duration_minutes from frontend is for scheduler's info, not direct offset
        # If claim_time_offset is mandatory, it needs to be calculated or passed.
        # For now, let's set it to 0 timedelta if it's not directly from user input.
        claim_time_offset=timedelta(minutes=0), # Default for now, scheduler will refine
        # scheduled_start is nullable, will be set by scheduler
        # is_locked is default False
    )
    db.add(new_bid)

    try:
        db.commit()
        db.refresh(user_points_entry) # Refresh to show updated points
        db.refresh(new_bid)
    except Exception as e:
        db.rollback()
        logger.error(f"Error placing bid for user {user.id} on spawn {spawn.name}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to place bid due to a database error.")

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "message": "Bid placed successfully!",
            "bid_id": new_bid.id,
            "current_points": float(user_points_entry.points) # Return updated points
        }
    )
