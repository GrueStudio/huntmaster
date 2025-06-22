from math import ceil
from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, distinct
from sqlalchemy.exc import IntegrityError
from typing import Optional
from datetime import datetime, timedelta, UTC, time
import pytz

from database import get_db
from models import World, Character, Spawn, SpawnProposal, ProposalStatus, SpawnChangeProposal, User, VoteType, Vote, user_spawn_favorites # Import necessary models and enums

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
router = APIRouter()

from templating import templates

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

    logged_in_user_id = request.session.get('user_id')

    characters_on_world = db.query(Character).filter(Character.world_id == world.id, Character.user_id == logged_in_user_id).all()
    unique_characters = db.query(Character).filter(Character.world_id == world.id).count()
    unique_users = db.query(Character.user_id).filter(Character.world_id == world.id).distinct().count()

    # Fetch all Spawns associated with this World
    spawns_in_world = db.query(Spawn).filter(Spawn.world_id == world.id).all() # Filter by world.id now

    # Fetch PENDING SpawnProposals for this world, ordered by creation time
    pending_spawn_proposals = db.query(SpawnProposal).filter(
        SpawnProposal.world_id == world.id,
        SpawnProposal.status == ProposalStatus.PENDING
    ).order_by(SpawnProposal.created_at.asc()).all()

    active_users_count = len(world.get_active_users(db))
    min_sponsors_required = min(world.sponsorship_flat, round(active_users_count * world.sposorship_fraction))

    # Initialize sponsored_proposal_ids and favorited_spawn_ids
    sponsored_proposal_ids = set()
    favorited_spawn_ids = set()

    # Get logged-in user ID for template rendering logic and fetching user-specific data


    if logged_in_user_id:
        # Fetch the user with their sponsored proposals (eager loading the relationship)
        # Note: 'User.favorited_spawns' is a placeholder. You'll need to define this
        # relationship and the associated join table in models.py for this to work.
        user = db.query(User).options(joinedload(User.sponsored_proposals)).filter(User.id == logged_in_user_id).first()
        if user:
            sponsored_proposal_ids = [p.id for p in user.sponsored_proposals]
            favorited_spawn_ids_query = db.query(user_spawn_favorites.c.spawn_id).filter(
                user_spawn_favorites.c.user_id == logged_in_user_id
            ).all()
            favorited_spawn_ids = [sid[0] for sid in favorited_spawn_ids_query]


    return templates.TemplateResponse(
        "world.html",
        {
            "request": request,
            "world": world,
            "unique_users_count": unique_users,
            "total_characters_count": unique_characters,
            "characters_on_world": characters_on_world,
            "min_sponsors_required": min_sponsors_required,
            "spawns": spawns_in_world,
            "pending_spawn_proposals": pending_spawn_proposals, # Pass pending proposals to template
            "logged_in_user_id": logged_in_user_id, # Pass logged-in user ID
            "sponsored_proposal_ids": sponsored_proposal_ids, # Pass sponsored proposal IDs
            "favorited_spawn_ids": favorited_spawn_ids # Pass favorited spawn IDs
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
    locking_time_mins: int = Form(..., alias='locking_time_mins'),
    claim_min_mins: int = Form(..., alias='claim_min_mins'),
    claim_max_mins: int = Form(..., alias='claim_max_mins'),
    deprioratize_time_mins: int = Form(..., alias="deprioratize_time_mins"),
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

    locking_period = timedelta(minutes=locking_time_mins)
    claim_time_min = timedelta(minutes=claim_min_mins)
    claim_time_max = timedelta(minutes=claim_max_mins)
    deprioritize_time = timedelta(minutes=deprioratize_time_mins)


    # Create the SpawnProposal in PENDING state
    new_proposal = SpawnProposal(
        name=spawn_name,
        description=spawn_description,
        world_id=world.id,
        min_level=min_level,
        max_level=max_level,
        locking_period=locking_period,
        claim_time_min=claim_time_min,
        claim_time_max=claim_time_max,
        deprioratize_time=deprioritize_time,
        status=ProposalStatus.PENDING, # Set to PENDING state
        created_at=datetime.now(UTC),
        # approved_at will be set only if/when the proposal is approved
    )

    db.add(new_proposal)
    db.commit()
    db.refresh(new_proposal)

    return RedirectResponse(url=f"/worlds/{world.name}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/worlds/{world_name}/spawns/{spawn_name}", response_class=HTMLResponse)
async def get_spawn_detail_page(
    request: Request,
    world_name: str,
    spawn_name: str,
    db: Session = Depends(get_db)
):
    """
    Displays a dedicated page for a specific spawn within a world.
    Both world_name and spawn_name lookups are case-insensitive.
    Also fetches and displays various types of spawn change proposals.
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

    # Fetch last approved permanent change proposal
    last_approved_permanent_proposal = db.query(SpawnChangeProposal).filter(
        SpawnChangeProposal.spawn_id == spawn.id,
        SpawnChangeProposal.status == ProposalStatus.APPROVED,
        SpawnChangeProposal.start_time.is_(None),
        SpawnChangeProposal.end_time.is_(None)
    ).order_by(SpawnChangeProposal.approved_at.desc()).first()

    # Fetch last approved temporary change proposal if it is currently in effect
    now_utc = datetime.now(UTC)
    last_approved_temporary_proposal = db.query(SpawnChangeProposal).filter(
        SpawnChangeProposal.spawn_id == spawn.id,
        SpawnChangeProposal.status == ProposalStatus.APPROVED,
        SpawnChangeProposal.start_time.isnot(None),
        SpawnChangeProposal.end_time.isnot(None),
        SpawnChangeProposal.start_time <= now_utc,
        SpawnChangeProposal.end_time >= now_utc
    ).order_by(SpawnChangeProposal.approved_at.desc()).first()

    # Fetch recently rejected AND approved proposals (displayed for a week)
    one_week_ago = now_utc - timedelta(days=7)
    recently_rejected_and_approved_proposals = db.query(SpawnChangeProposal).filter(
        SpawnChangeProposal.spawn_id == spawn.id,
        SpawnChangeProposal.status.in_([ProposalStatus.REJECTED, ProposalStatus.APPROVED]), # Modified filter
        SpawnChangeProposal.approved_at >= one_week_ago # Assuming approved_at is used for rejection/approval timestamp
    ).order_by(SpawnChangeProposal.approved_at.desc()).all()


    # Fetch currently pending proposals (limit to 3, scrollable)
    pending_proposals_raw = db.query(SpawnChangeProposal).filter(
        SpawnChangeProposal.spawn_id == spawn.id,
        SpawnChangeProposal.status == ProposalStatus.PENDING
    ).order_by(SpawnChangeProposal.created_at.asc()).limit(3).all()

    # Get logged-in user ID for template rendering logic and fetching user-specific data
    logged_in_user_id = request.session.get('user_id')

    # Prepare pending proposals with user's vote status
    pending_proposals = []
    if logged_in_user_id:
        # Eager load the spawn_change_proposals_voted to get the vote type
        user = db.query(User).options(joinedload(User.spawn_change_proposals_voted)).filter(User.id == logged_in_user_id).first()
        if user:
            # Query the proposal_votes association table directly for user's votes
            user_vote_records = db.query(Vote).filter(Vote.user_id == logged_in_user_id).all()

            # Create a dictionary to quickly look up user's vote for each proposal
            user_votes = {record.spawn_change_proposal_id: record.vote_type.value for record in user_vote_records}

            for proposal in pending_proposals_raw:
                # Check if the user has voted on this specific proposal
                proposal.user_vote = user_votes.get(proposal.id)
                pending_proposals.append(proposal)
        else:
            # If user not found (e.g., session stale), treat as not logged in for voting purposes
            for proposal in pending_proposals_raw:
                proposal.user_vote = None
                pending_proposals.append(proposal)
    else:
        for proposal in pending_proposals_raw:
            proposal.user_vote = None
            pending_proposals.append(proposal)

    # Helper to calculate engagement and favorability for proposals
    def calculate_proposal_stats(proposal):
        votes_for = proposal.votes_for # Access hybrid property
        votes_against = proposal.votes_against # Access hybrid property

        engagement = votes_for + votes_against
        favorability = 0.0
        if engagement > 0:
            favorability = (votes_for / engagement) * 100

        return {
            "engagement": engagement,
            "favorability": round(favorability, 2) # Round to 2 decimal places
        }

    # Attach stats to proposals
    if last_approved_permanent_proposal:
        last_approved_permanent_proposal.stats = calculate_proposal_stats(last_approved_permanent_proposal)
    if last_approved_temporary_proposal:
        last_approved_temporary_proposal.stats = calculate_proposal_stats(last_approved_temporary_proposal)
    for proposal in recently_rejected_and_approved_proposals: # Apply to the combined list
        proposal.stats = calculate_proposal_stats(proposal)
    for proposal in pending_proposals:
        proposal.stats = calculate_proposal_stats(proposal)

    return templates.TemplateResponse(
        "spawn_detail.html",
        {
            "request": request,
            "world": world,
            "spawn": spawn,
            "last_approved_permanent_proposal": last_approved_permanent_proposal,
            "last_approved_temporary_proposal": last_approved_temporary_proposal,
            "recently_rejected_proposals": recently_rejected_and_approved_proposals, # Pass the combined list
            "pending_proposals": pending_proposals,
            "now_utc": now_utc, # Pass current UTC time for template logic
            "logged_in_user_id": logged_in_user_id # Pass for frontend logic
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

    world = spawn_proposal.world

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


    active_users_count = len(world.get_active_users(db))
    min_sponsors_required = min(world.sponsorship_flat, round(active_users_count * world.sposorship_fraction))

    # Check if the proposal meets the approval threshold
    if spawn_proposal.num_sponsors >= min_sponsors_required:
        spawn_proposal.status = ProposalStatus.APPROVED
        spawn_proposal.approved_at = datetime.now(UTC)

        # Create the actual Spawn if the proposal is approved
        new_spawn = Spawn(
            name=spawn_proposal.name,
            description=spawn_proposal.description,
            world_id=spawn_proposal.world_id,
            # min_level=spawn_proposal.min_level,
            # max_level=spawn_proposal.max_level,
            # Hardcoded defaults for fields not in SpawnProposal model (for now)
            # These fields need to be added to SpawnProposal model for full configurability
            locking_period=spawn_proposal.locking_period, # Default value
            claim_time_min=spawn_proposal.claim_time_min,         # Default value
            claim_time_max=spawn_proposal.claim_time_max,        # Default value
            deprioratize_time=spawn_proposal.deprioratize_time,   # Default value
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
                # "min_level": new_spawn.min_level,
                # "max_level": new_spawn.max_level,
                "locking_period": new_spawn.locking_period.minutes,
                "claim_time_min": new_spawn.claim_time_min.minutes,
                "claim_time_max": new_spawn.claim_time_max.minutes,
                "deprioratize_time": new_spawn.deprioratize_time.minutes
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

@router.post("/worlds/{world_name}/spawns/{spawn_name}/vote", status_code=status.HTTP_200_OK)
async def vote_on_spawn_change_proposal(
    request: Request,
    world_name: str,
    spawn_name: str,
    proposal_id: int = Form(...),
    raw_vote_type: str = Form(..., alias="vote_type"), # Receive as string
    db: Session = Depends(get_db)
):
    """
    Handles casting a vote (upvote/downvote) on a spawn change proposal.
    Evaluates proposal status based on vote thresholds.
    """
    user_id = request.session.get('user_id')
    if not user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You must be logged in to vote on proposals.")

    try:
        vote_type = VoteType(raw_vote_type.lower()) # Convert to enum, case-insensitively
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid vote type. Must be 'upvote' or 'downvote'.")


    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    # Modified query to join with World and filter correctly
    spawn = db.query(Spawn).join(World).filter(
        func.lower(Spawn.name) == spawn_name.lower(),
        func.lower(World.name) == world_name.lower()
    ).first()
    if not spawn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Spawn not found.")

    proposal = db.query(SpawnChangeProposal).filter(
        SpawnChangeProposal.id == proposal_id,
        SpawnChangeProposal.spawn_id == spawn.id
    ).first()
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Spawn change proposal not found for this spawn.")

    # Check if the proposal is still pending
    if proposal.status != ProposalStatus.PENDING:
        return {"message": f"This proposal is already {proposal.status.value}.", "proposal_id": proposal_id, "status": proposal.status.value}

    # Check if the user has already voted on this proposal
    # We need to query the association table directly for the user's vote
    existing_vote_record = db.query(Vote).filter(Vote.user_id == user_id, Vote.proposal_id == proposal_id).first()

    if existing_vote_record:
        # User has already voted. Decide if re-voting is allowed or simply return a message.
        # For now, let's just inform them they've already voted.
        return {"message": "You have already voted on this proposal.", "proposal_id": proposal_id, "status": "already_voted", "your_vote": existing_vote_record.vote_type.value}

    try:
        # Add the vote record to the association table
        vote = Vote(user = user, proposal = proposal, vote_type=vote_type)

        db.add(vote)
        db.add(proposal) # Add proposal back to session to mark it for update
        db.commit()
        db.refresh(proposal) # Refresh to get updated vote counts

        # --- Evaluate Proposal Thresholds ---
        MIN_TOTAL_VOTES_FOR_EVALUATION = 5 # Minimum total votes before evaluation
        APPROVAL_PERCENTAGE_THRESHOLD = 75 # 75% upvotes for approval

        if proposal.total_votes >= MIN_TOTAL_VOTES_FOR_EVALUATION:
            favorability = (proposal.votes_for / proposal.total_votes) * 100

            if favorability >= APPROVAL_PERCENTAGE_THRESHOLD:
                # Proposal approved! Apply changes to the Spawn.
                proposal.status = ProposalStatus.APPROVED
                proposal.approved_at = datetime.now(UTC)
                spawn.locking_period_minutes = proposal.new_locking_period
                spawn.claim_time_min = proposal.new_claim_time_min
                spawn.claim_time_max = proposal.new_claim_time_max
                # For temporary changes, you might need more complex logic
                # For now, apply directly.
                db.add(spawn)
                db.add(proposal)
                db.commit()
                return {
                    "message": "Vote cast successfully! Proposal APPROVED and changes applied.",
                    "proposal_id": proposal_id,
                    "status": "approved",
                    "your_vote": vote_type.value,
                    "current_votes_for": proposal.votes_for, # Return current counts
                    "current_votes_against": proposal.votes_against,
                    "total_votes": proposal.total_votes,
                    "favorability": round(favorability, 2)
                }
            else:
                # Proposal rejected due to not meeting approval percentage
                proposal.status = ProposalStatus.REJECTED
                proposal.approved_at = datetime.now(UTC) # Use approved_at for rejection timestamp too
                db.add(proposal)
                db.commit()
                return {
                    "message": "Vote cast successfully! Proposal REJECTED (did not meet approval threshold).",
                    "proposal_id": proposal_id,
                    "status": "rejected",
                    "your_vote": vote_type.value,
                    "current_votes_for": proposal.votes_for, # Return current counts
                    "current_votes_against": proposal.votes_against,
                    "total_votes": proposal.total_votes,
                    "favorability": round(favorability, 2)
                }
        else:
            # Not enough total votes yet, remains pending
            db.commit() # Commit the vote even if not approved yet
            return {
                "message": f"Vote cast successfully! Proposal is still PENDING. Needs {MIN_TOTAL_VOTES_FOR_EVALUATION - proposal.total_votes} more votes to be evaluated.",
                "proposal_id": proposal_id,
                "status": "pending",
                "your_vote": vote_type.value,
                "current_votes_for": proposal.votes_for,
                "current_votes_against": proposal.votes_against,
                "total_votes": proposal.total_votes,
                "favorability": round((proposal.votes_for / proposal.total_votes) * 100, 2) if proposal.total_votes > 0 else 0.0
            }

    except IntegrityError as e:
        db.rollback()
        # This could happen if a concurrent vote was cast or there's an issue with the association table.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Database error while recording vote: {e.orig}")
    except Exception as e:
        db.rollback()
        logger.info(f"Error during vote submission: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while casting your vote.")


@router.post("/worlds/{world_name}/spawns/{spawn_name}/propose", response_class=HTMLResponse)
async def post_propose_spawn_change(
    request: Request,
    world_name: str,
    spawn_name: str,
    spawn_id: int = Form(...),
    locking_period_minutes: int = Form(...),
    claim_time_min: int = Form(...),
    claim_time_max: int = Form(...),
    temporary_change_toggle: Optional[str] = Form(None), # Checkbox sends 'on' if checked, None if unchecked
    start_date: Optional[str] = Form(None), # Date string 'YYYY-MM-DD'
    end_date: Optional[str] = Form(None),   # Date string 'YYYY-MM-DD'
    db: Session = Depends(get_db)
):
    """
    Handles the actual submission and processing of SpawnChangeProposals.
    Creates a new SpawnChangeProposal in the database.
    """
    user_id = request.session.get('user_id')
    if not user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You must be logged in to propose changes.")

    world = db.query(World).filter(func.lower(World.name) == world_name.lower()).first()
    if not world:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="World not found")

    spawn = db.query(Spawn).filter(
        func.lower(Spawn.name) == spawn_name.lower(),
        Spawn.world_id == world.id,
        Spawn.id == spawn_id # Ensure the ID matches for robustness
    ).first()
    if not spawn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Spawn not found in this world with the provided ID.")

    # Prepare start_time and end_time based on toggle and date inputs
    proposal_start_time = None
    proposal_end_time = None

    if temporary_change_toggle == 'on':
        berlin_tz = pytz.timezone('Europe/Berlin')
        if start_date:
            # Parse YYYY-MM-DD string into a naive date object
            start_date_part_naive = datetime.strptime(start_date, '%Y-%m-%d').date()
            # Combine with a time (e.g., 10:00) to create a naive datetime
            naive_start_datetime = datetime.combine(start_date_part_naive, time(10, 0, 0))
            # Localize the naive datetime to Berlin timezone, handling DST
            localized_start_datetime = berlin_tz.localize(naive_start_datetime)
            # Convert the localized datetime to UTC
            proposal_start_time = localized_start_datetime.astimezone(UTC)

        if end_date:
            end_date_part_naive = datetime.strptime(end_date, '%Y-%m-%d').date()
            naive_end_datetime = datetime.combine(end_date_part_naive, time(10, 0, 0))
            localized_end_datetime = berlin_tz.localize(naive_end_datetime)
            proposal_end_time = localized_end_datetime.astimezone(UTC)

        # Basic validation for temporary change dates
        if proposal_start_time and proposal_end_time and proposal_start_time >= proposal_end_time:
            error_message = "End date must be after start date for temporary changes."
            return RedirectResponse(
                url=f"/worlds/{world.name}/spawns/{spawn.name}/propose?error={error_message}",
                status_code=status.HTTP_303_SEE_OTHER
            )
        elif (proposal_start_time is None and proposal_end_time is not None) or \
             (proposal_start_time is not None and proposal_end_time is None):
            error_message = "Both start and end dates must be provided for a temporary change."
            return RedirectResponse(
                url=f"/worlds/{world.name}/spawns/{spawn.name}/propose?error={error_message}",
                status_code=status.HTTP_303_SEE_OTHER
            )

    try:
        # Create a new SpawnChangeProposal instance
        new_change_proposal = SpawnChangeProposal(
            name=f"Change for {spawn.name}", # Use spawn name for proposal name
            description=spawn.description, # Use current spawn description for proposal description
            spawn_id=spawn.id,
            new_locking_period=locking_period_minutes,
            new_claim_time_min=claim_time_min,
            new_claim_time_max=claim_time_max,
            start_time=proposal_start_time, # Will be None if toggle is off
            end_time=proposal_end_time,     # Will be None if toggle is off
            status=ProposalStatus.PENDING,
            created_at=datetime.now(UTC)
        )

        db.add(new_change_proposal)
        db.commit()
        db.refresh(new_change_proposal)

        message_text = "Your spawn change proposal has been successfully submitted for review!"
        return RedirectResponse(
            url=f"/worlds/{world.name}/spawns/{spawn.name}?message={message_text}",
            status_code=status.HTTP_303_SEE_OTHER
        )

    except IntegrityError as e:
        db.rollback()
        # You might want to log the full error `e` for debugging
        error_message = f"A database integrity error occurred while submitting your proposal: {e.orig}"
        return RedirectResponse(
            url=f"/worlds/{world.name}/spawns/{spawn.name}/propose?error={error_message}",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except Exception as e:
        db.rollback()
        logger.info(f"Error during spawn change proposal submission: {e}") # Log the full error
        error_message = "An unexpected error occurred during your proposal submission."
        return RedirectResponse(
            url=f"/worlds/{world.name}/spawns/{spawn.name}/propose?error={error_message}",
            status_code=status.HTTP_303_SEE_OTHER
        )
