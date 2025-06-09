from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct
from datetime import datetime, timedelta, UTC

from database import get_db
from models import World, Character, Spawn, SpawnProposal, ProposalStatus, User # Import necessary models and enums

router = APIRouter()

# Configure Jinja2Templates (assuming templates directory is relative to app root or defined globally in main.py)
templates = Jinja2Templates(directory="templates")

@router.get("/worlds/{world_name}", response_class=HTMLResponse)
async def get_world_page(
    request: Request,
    world_name: str,
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
        Character.world_id == world.id,
        Character.user_id.isnot(None) # Only count characters assigned to a user
    ).scalar()

    # Calculate the total number of characters in this world
    total_characters_in_world = db.query(func.count(Character.id)).filter(
        Character.world_id == world.id
    ).scalar()

    # Fetch all Spawns associated with this World
    spawns_in_world = db.query(Spawn).filter(Spawn.world_id == world.id).all()

    return templates.TemplateResponse(
        "world.html",
        {
            "request": request,
            "world": world,
            "unique_users_count": unique_users_in_world,
            "total_characters_count": total_characters_in_world,
            "spawns": spawns_in_world
        }
    )

@router.get("/spawns/{world_name}/propose-spawn", response_class=HTMLResponse)
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

@router.post("/spawns/{world_name}/propose-spawn", response_class=HTMLResponse)
async def post_propose_spawn(
    request: Request,
    world_name: str,
    spawn_name: str = Form(..., alias="name"), # Get 'name' from form data
    spawn_description: str = Form(None, alias="description"), # Get 'description' from form data
    db: Session = Depends(get_db)
):
    """
    Handles the submission of a new spawn proposal.
    Creates an APPROVED SpawnProposal and a new Spawn.
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

    # Check if a spawn with this name already exists in this world
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
                "message": "Please try a different name."
            }
        )

    # Create the SpawnProposal in APPROVED state
    new_proposal = SpawnProposal(
        name=spawn_name,
        description=spawn_description,
        world_id=world.id,
        min_level=1, # Default values
        max_level=1000, # Default values
        status=ProposalStatus.APPROVED, # Set to APPROVED state
        created_at=datetime.now(UTC),
        approved_at=datetime.now(UTC), # Set approved_at since it's approved
    )

    db.add(new_proposal)
    db.flush() # Flush to get the ID for new_proposal before creating Spawn

    # Create the actual Spawn
    new_spawn = Spawn(
        name=spawn_name,
        description=spawn_description,
        world_id=world.id,
        locking_period=15, # 15 minutes
        claim_time_min=15, # 15 minutes
        claim_time_max=180, # 3 hours (180 minutes)
        proposal_id=new_proposal.id, # Link to the proposal
    )

    db.add(new_spawn)
    db.flush() # Flush to ensure new_spawn gets its ID

    # Link the SpawnProposal to the newly created Spawn
    new_proposal.spawn_id = new_spawn.id

    db.commit()
    db.refresh(new_proposal)
    db.refresh(new_spawn)

    return templates.TemplateResponse(
        "propose_spawn.html",
        {
            "request": request,
            "world_name": world_name,
            "success": f"Spawn '{spawn_name}' in {world.name} has been successfully proposed and approved!",
            "message": "You can now view it in the world's spawn list."
        }
    )
