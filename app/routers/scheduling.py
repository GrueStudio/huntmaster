# /app/routers/scheduling.py

from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta, UTC

from database import get_db
from models import World, Character, Spawn, SpawnChangeProposal, ProposalStatus, User, Points # Import Points model
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
    and the character's current points for that spawn.
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

    # 4. Fetch character and spawn-specific points
    # Assuming a user has at least one character in this world for bidding purposes
    # If a user can have multiple characters in a world, you'd need a way to select the active character.
    character = db.query(Character).filter(
        Character.user_id == user.id,
        Character.world_id == world.id
    ).first()

    if not character:
        # This scenario might need a different handling, e.g., redirect to character creation
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found for this user in this world.")

    # Get spawn-specific points for the character
    character_spawn_points_entry = db.query(Points).filter(
        Points.character_id == character.id,
        Points.spawn_id == spawn.id
    ).first()

    current_points_for_spawn = 0.0
    if character_spawn_points_entry:
        current_points_for_spawn = character_spawn_points_entry.points
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
        "bid_form.html", # Assuming your HTML is named this
        {
            "request": request,
            "current_user": user, # Pass the user object for layout macro
            "world_name": world.name,
            "spawn_name": spawn.name,
            "spawn_id": spawn.id, # Pass spawn_id for form submission
            "character_id": character.id, # Pass character_id for form submission
            "bid_settings": bid_settings, # Min/max claim duration
            "current_points_for_spawn": current_points_for_spawn, # Current points for this spawn
            "breadcrumbs": breadcrumbs
        }
    )
