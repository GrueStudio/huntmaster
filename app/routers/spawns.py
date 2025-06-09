from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct

from database import get_db
from models import World, Character, Spawn # Import necessary models

router = APIRouter()

# Configure Jinja2Templates (assuming templates directory is relative to app root or defined globally in main.py)
templates = Jinja2Templates(directory="templates")

@router.get("/spawns/{world_name}", response_class=HTMLResponse) # Changed path to use world_name
async def get_world_page(
    request: Request,
    world_name: str, # Changed parameter name to world_name
    db: Session = Depends(get_db)
):
    """
    Displays a dedicated page for a specific game world, showing its details,
    character statistics, and a list of associated spawns.
    """
    # Fetch the World object by name
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
async def get_propose_spawn_form(request: Request, world_name: str, db: Session = Depends(get_db)):
    """
    Displays the form for proposing a new spawn.
    (Placeholder - actual form and submission logic to be developed later)
    """
    # For now, just a simple message. This will be a full form later.
    return templates.TemplateResponse("propose_spawn.html", {"request": request, "message": "Propose a New Spawn Here!"})
