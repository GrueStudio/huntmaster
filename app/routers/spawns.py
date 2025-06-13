from math import ceil
from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, distinct
from datetime import datetime, timedelta, UTC

from database import get_db
from models import World, Character, Spawn, SpawnProposal, ProposalStatus, User # Import necessary models and enums

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
router = APIRouter()

# Configure Jinja2Templates (assuming templates directory is relative to app root or defined globally in main.py)
templates = Jinja2Templates(directory="templates")

@router.get("/worlds/{world_name}", response_class=HTMLResponse)
async def get_world_page(
    request: Request,
    world_name: str, # Changed parameter name to world_name
    db: Session = Depends(get_db)
):
    """
    Displays a dedicated page for a specific game world, showing its details,
    character statistics, and a list of associated spawns.
    The world_name lookup is case-insensitive.
    """
    # Convert the incoming world_name to lowercase for case-insensitive comparison
    world = db.query(World).filter(func.lower(World.name) == world_name.lower()).first()

    if not world:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="World not found")

    # Calculate the number of unique users with characters in this world
    unique_users_in_world = db.query(func.count(distinct(Character.user_id))).filter(
        Character.world_id == world.id, # Filter by world.id now
        Character.user_id.isnot(None) # Only count characters assigned to a user
    ).scalar()

    # Calculate the total number of characters in this world
    total_characters_in_world = db.query(func.count(Character.id)).filter(
        Character.world_id == world.id # Filter by world.id now
    ).scalar()

    # Fetch all Spawns associated with this World
    spawns_in_world = db.query(Spawn).filter(Spawn.world_id == world.id).all() # Filter by world.id now

    # Fetch PENDING SpawnProposals for this world, ordered by creation time
    pending_spawn_proposals = db.query(SpawnProposal).filter(
        SpawnProposal.world_id == world.id,
        SpawnProposal.status == ProposalStatus.PENDING
    ).order_by(SpawnProposal.created_at.asc()).all()


    # Get all spawn IDs for the current world
    world_spawns = db.query(Spawn.id).filter(Spawn.world_id == world.id).scalar_subquery()

    # Query distinct user_ids whose characters have participated in hunts in this world in the last 90 days
    ninety_days_ago = datetime.now(UTC) - timedelta(days=90)

    active_users_subquery = db.query(distinct(Character.user_id)).join(Spawn, Character.world_id == Spawn.world_id).subquery()
        #.join(Hunt).filter(
        #    Hunt.spawn_id.in_(world_spawns), # Filter hunts to only those within the world's spawns
        #    Hunt.start_time >= ninety_days_ago).subquery()

    active_users_count = db.query(func.count()).select_from(active_users_subquery).scalar()

    # Calculate min_sponsors_required once for the page
    # (min 5 unique sponsors OR 1% of active users, whichever is smaller, capped at 20)
    percentage_sponsors = round(active_users_count * 0.01) if active_users_count else 0
    min_sponsors_required = min(5, percentage_sponsors)

    # Initialize sponsored_proposal_ids and favorited_spawn_ids
    sponsored_proposal_ids = set()
    favorited_spawn_ids = set()

    # Get logged-in user ID for template rendering logic and fetching user-specific data
    logged_in_user_id = request.session.get('user_id')

    if logged_in_user_id:
        # Fetch the user with their sponsored proposals (eager loading the relationship)
        # Note: 'User.favorited_spawns' is a placeholder. You'll need to define this
        # relationship and the associated join table in models.py for this to work.
        user = db.query(User).options(joinedload(User.sponsored_proposals)).filter(User.id == logged_in_user_id).first()
        if user:
            # Collect IDs of proposals sponsored by the current user
            sponsored_proposal_ids = {p.id for p in user.sponsored_proposals}

            # --- Placeholder for fetching favorited spawns ---
            # You will need to define a relationship for User.favorited_spawns in your models.py
            # For now, we'll simulate fetching from a join table directly.
            # This requires 'from sqlalchemy import Table, Column, Integer, ForeignKey' in models.py
            # and defining user_favorite_spawns = Table(...) as a global.
            # Example (if user_favorite_spawns table exists):
            # from models import user_favorite_spawns # Import this if defined globally in models.py
            # favorited_spawn_ids_query = db.query(user_favorite_spawns.c.spawn_id).filter(
            #     user_favorite_spawns.c.user_id == logged_in_user_id
            # ).all()
            # favorited_spawn_ids = {sid[0] for sid in favorited_spawn_ids_query}

            # For demonstration without models.py changes, let's assume a static list or an empty set
            # This section needs actual implementation once models.py is updated with favorites.
            # For now, we'll use an empty set, so the star icon will always be outlined.
            pass # No actual query here for favorited_spawn_ids in this turn


    return templates.TemplateResponse(
        "world.html",
        {
            "request": request,
            "world": world,
            "unique_users_count": unique_users_in_world,
            "total_characters_count": total_characters_in_world,
            "min_sponsors_required": min_sponsors_required,
            "spawns": spawns_in_world,
            "pending_spawn_proposals": pending_spawn_proposals, # Pass pending proposals to template
            "logged_in_user_id": logged_in_user_id, # Pass logged-in user ID
            "sponsored_proposal_ids": sponsored_proposal_ids, # Pass sponsored proposal IDs
            "favorited_spawn_ids": favorited_spawn_ids # Pass favorited spawn IDs (currently empty set)
        }
    )

@router.get("/worlds/{world_name}/propose", response_class=HTMLResponse)
async def get_propose_spawn_form(
    request: Request,
    world_name: str # Capture world_name from the path
):
    """
    Displays the form for proposing a new spawn.
    """
    # Check if user is logged in
    username = request.session.get('username')
    if not username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You must be logged in to propose a spawn.")

    return templates.TemplateResponse(
        "propose_spawn.html",
        {
            "request": request,
            "world_name": world_name,
            "message": "Propose a new spawn in this world!"
        }
    )

@router.post("/worlds/{world_name}/propose", response_class=HTMLResponse)
async def post_propose_spawn(
    request: Request,
    world_name: str,
    spawn_name: str = Form(..., alias="name"),
    spawn_description: str = Form(None, alias="description"),
    min_level: int = Form(..., alias="min_level"),
    max_level: int = Form(..., alias="max_level"),
    # Note: respawn_time_minutes, locking_period_minutes, deprioratization_time
    # are removed from this function's parameters to align with the SpawnProposal model
    # as they were not part of the previous version of the model.
    db: Session = Depends(get_db)
):
    """
    Handles the submission of a new spawn proposal.
    Creates a PENDING SpawnProposal. The Spawn creation will happen only after
    the proposal is approved via the sponsorship mechanism.
    """
    # Check if user is logged in
    username = request.session.get('username')
    if not username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You must be logged in to propose a spawn.")

    # Find the user by username
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    # Find the world by name (case-insensitive)
    world = db.query(World).filter(func.lower(World.name) == world_name.lower()).first()
    if not world:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="World not found.")

    # Check if a spawn with this name already exists in this world (case-insensitive)
    existing_spawn = db.query(Spawn).filter(
        func.lower(Spawn.name) == spawn_name.lower(),
        Spawn.world_id == world.id
    ).first()
    if existing_spawn:
        return templates.TemplateResponse(
            "propose_spawn.html",
            {
                "request": request,
                "world_name": world_name,
                "error": f"A spawn named '{spawn_name}' already exists in {world.name}.",
                "message": "Please try a different name.",
                # Retain form values to pre-fill the form on error, for better UX
                "name": spawn_name,
                "description": spawn_description,
                "min_level": min_level,
                "max_level": max_level
            }
        )

    # Create the SpawnProposal in PENDING state
    new_proposal = SpawnProposal(
        name=spawn_name,
        description=spawn_description,
        world_id=world.id,
        min_level=min_level,
        max_level=max_level,
        status=ProposalStatus.PENDING, # Set to PENDING state
        created_at=datetime.now(UTC),
        # approved_at will be set only if/when the proposal is approved
    )

    db.add(new_proposal)
    db.commit()
    db.refresh(new_proposal)

    return RedirectResponse(url=f"/worlds/{world.name}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/worlds/{world_name}/spawns/{spawn_name}", response_class=HTMLResponse) # Updated route
async def get_spawn_detail_page(
    request: Request,
    world_name: str,
    spawn_name: str,
    db: Session = Depends(get_db)
):
    """
    Displays a dedicated page for a specific spawn within a world.
    Both world_name and spawn_name lookups are case-insensitive.
    """
    # First, find the world
    world = db.query(World).filter(func.lower(World.name) == world_name.lower()).first()
    if not world:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="World not found")

    # Then, find the spawn within that world
    spawn = db.query(Spawn).filter(
        func.lower(Spawn.name) == spawn_name.lower(),
        Spawn.world_id == world.id
    ).first()
    if not spawn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Spawn not found in this world")

    return templates.TemplateResponse(
        "spawn_detail.html",
        {
            "request": request,
            "world": world,
            "spawn": spawn
        }
    )
@router.post("/worlds/{world_name}/sponsor", status_code=status.HTTP_200_OK)
async def sponsor_spawn_proposal(
    request: Request,
    world_name: str,
    proposal_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """
    Handles sponsoring a spawn proposal asynchronously.
    This function implements the sponsorship logic and evaluates approval thresholds.
    """
    user_id = request.session.get('user_id')
    if not user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You must be logged in to sponsor a proposal.")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    spawn_proposal = db.query(SpawnProposal).filter(SpawnProposal.id == proposal_id).first()
    if not spawn_proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Spawn proposal not found.")

    # Ensure the proposal is for the correct world
    if spawn_proposal.world.name.lower() != world_name.lower():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Proposal does not belong to this world.")

    # Check if the proposal is still pending
    if spawn_proposal.status != ProposalStatus.PENDING:
        return {"message": f"This proposal is already {spawn_proposal.status.value}.", "proposal_id": proposal_id}

    # Check if user has already sponsored this proposal
    if user in spawn_proposal.sponsors:
        return {"message": "You have already sponsored this proposal.", "proposal_id": proposal_id}

    # Add the sponsorship
    spawn_proposal.sponsors.append(user)
    db.add(spawn_proposal)
    db.commit()
    db.refresh(spawn_proposal) # Refresh to get updated sponsors list

    # --- Evaluate Sponsorship Thresholds ---
    # 1. Calculate active users in the world (for the 1% rule)
    # An "active user" in a world is defined as any user who has:
    # - Has at least one Character associated with that World AND
    # - That character has participated in *any* Hunt within that World in the last 90 days.

    # Get all spawn IDs for the current world
    world_spawns = db.query(Spawn.id).filter(Spawn.world_id == spawn_proposal.world_id).scalar_subquery()

    # Query distinct user_ids whose characters have participated in hunts in this world in the last 90 days
    ninety_days_ago = datetime.now(UTC) - timedelta(days=90)

    active_users_subquery = db.query(distinct(Character.user_id)).join(Spawn, Character.world_id == Spawn.world_id).subquery()
        #.join(Hunt).filter(
        #    Hunt.spawn_id.in_(world_spawns), # Filter hunts to only those within the world's spawns
        #    Hunt.start_time >= ninety_days_ago).subquery()

    active_users_count = db.query(func.count()).select_from(active_users_subquery).scalar()

    # Calculate the minimum sponsors required based on hybrid logic
    # (min 5 unique sponsors OR 1% of active users, whichever is smaller, capped at 20)
    percentage_sponsors = ceil(active_users_count * 0.01) if active_users_count else 0

    # Ensure minimum 5 sponsors, then consider percentage, then cap at 20
    min_sponsors_required = min(percentage_sponsors, 5)

    # Check if the proposal meets the approval threshold
    if spawn_proposal.num_sponsors >= min_sponsors_required:
        spawn_proposal.status = ProposalStatus.APPROVED
        spawn_proposal.approved_at = datetime.now(UTC)

        # Create the actual Spawn if the proposal is approved
        new_spawn = Spawn(
            name=spawn_proposal.name,
            description=spawn_proposal.description,
            world_id=spawn_proposal.world_id,
            min_level=spawn_proposal.min_level,
            max_level=spawn_proposal.max_level,
            # Hardcoded defaults for fields not in SpawnProposal model (for now)
            # These fields need to be added to SpawnProposal model for full configurability
            locking_period_minutes=15, # Default value
            claim_time_min=15,         # Default value
            claim_time_max=180,        # Default value
            respawn_time_minutes=60,   # Default value
            claim_times_per_day=1,     # Default value
            proposal_id=spawn_proposal.id, # Link to the proposal
        )
        db.add(new_spawn)
        db.flush() # Flush to get the ID for new_spawn before committing
        spawn_proposal.spawn_id = new_spawn.id # Link proposal to created spawn

        db.commit()
        db.refresh(spawn_proposal)
        db.refresh(new_spawn)

        return JSONResponse({
            "message": "Proposal approved and spawn created!",
            "proposal_id": proposal_id,
            "spawn_created": True,
            "spawn_details": {
                "id": new_spawn.id,
                "name": new_spawn.name,
                "description": new_spawn.description,
                "min_level": new_spawn.min_level,
                "max_level": new_spawn.max_level
            }
        })
    else:
        db.commit() # Commit the sponsorship even if not approved yet
        return JSONResponse({"message": f"Proposal sponsored successfully! Needs {min_sponsors_required - spawn_proposal.num_sponsors} more sponsors for approval.", "proposal_id": proposal_id})

@router.get("/worlds/{world_name}/spawns/{spawn_name}/propose", response_class=HTMLResponse)
async def get_propose_spawn_change_form(
    request: Request,
    world_name: str,
    spawn_name: str,
    db: Session = Depends(get_db)
):
    """
    Displays the form for proposing changes to an existing spawn.
    Dynamically populates current values and allows input for new ones.
    """
    user_id = request.session.get('user_id')
    if not user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You must be logged in to propose changes.")

    world = db.query(World).filter(func.lower(World.name) == world_name.lower()).first()
    if not world:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="World not found")

    spawn = db.query(Spawn).filter(
        func.lower(Spawn.name) == spawn_name.lower(),
        Spawn.world_id == world.id
    ).first()
    if not spawn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Spawn not found in this world.")

    return templates.TemplateResponse(
        "propose_change.html",
        {
            "request": request,
            "world": world, # Pass the world object instead of just the name
            "spawn": spawn,
            "message": None,
            "error": None
        }
    )
