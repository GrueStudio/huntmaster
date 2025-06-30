import os, time
from datetime import datetime, UTC
import httpx # Import httpx for making async HTTP requests

from fastapi import FastAPI, Request, status, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from templating import templates
from fastapi.staticfiles import StaticFiles
from models import User, Spawn, World

from sqlalchemy.orm import Session, selectinload
from starlette.middleware.sessions import SessionMiddleware

# Assuming database.py and models.py are in the same 'app' directory
from database import get_db
from routers import accounts, characters, spawns, scheduling # Import the new routers

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI()

# Add SessionMiddleware for session management
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET_KEY", "a-very-secret-key"))

# Mount the static directory
app.mount("/static", StaticFiles(directory="static"), name="static")



# --- Helper Function for Timezone Conversion ---
def convert_to_utc_naive(dt: datetime) -> datetime:
    """
    Converts a datetime object to a timezone-naive UTC datetime.
    """
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    else:
        return dt # Assuming naive inputs are already UTC for simplicity here.


# --- World Update Function ---
async def update_worlds_from_tibiadata(db: Session):
    """
    Fetches world data from TibiaData.com API and updates the local World table.
    """
    TIBIADATA_WORLDS_API = "https://api.tibiadata.com/v4/worlds"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(TIBIADATA_WORLDS_API)
            response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
            data = response.json()

        worlds_data = data.get('worlds', {}).get('regular_worlds', []) + data.get('worlds', {}).get('tournament_worlds', []) # Include tournament worlds too

        for world_info in worlds_data:
            world_name = world_info.get('name')
            world_location = world_info.get('location') # TibiaData provides location

            if world_name:
                existing_world = db.query(World).filter(World.name == world_name).first()
                if existing_world:
                    # Update existing world's location if it changed
                    if existing_world.location != world_location:
                        existing_world.location = world_location
                        db.add(existing_world)
                        logger.info(f"Updated world: {world_name}")
                else:
                    # Add new world
                    new_world = World(name=world_name, location=world_location)
                    db.add(new_world)
                    logger.info(f"Added new world: {world_name}")

        db.commit()
        logger.info("World data updated successfully from TibiaData.com.")

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error updating worlds from TibiaData: {e.response.status_code} - {e.response.text}")
        db.rollback()
    except httpx.RequestError as e:
        logger.error(f"Network error updating worlds from TibiaData: {e}")
        db.rollback()
    except Exception as e:
        logger.error(f"An unexpected error occurred while updating worlds: {e}")
        db.rollback()


# --- Database Initialization (for development/testing) ---
@app.on_event("startup")
async def on_startup():
    # Call the world update function on startup
    db_session = next(get_db()) # Get a session for the startup event
    try:
        await update_worlds_from_tibiadata(db_session)
    finally:
        db_session.close()


@app.on_event("shutdown")
async def on_shutdown():
    pass


# --- Include Routers ---
app.include_router(accounts.router)
app.include_router(characters.router)
app.include_router(spawns.router)
app.include_router(scheduling.router)

# --- Main Routes ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    if 'username' in request.session:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    start_time_total = time.time() # Start timing for the entire request

    username = request.session.get('username')
    user_id = request.session.get('user_id')

    if not username or not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    start_time_db = time.time() # Start timing for DB query
    user = db.query(User).options(selectinload(User.favourite_spawns).joinedload(Spawn.world)).filter(User.id == user_id).first()
    end_time_db = time.time() # End timing for DB query
    logger.info(f"Dashboard DB query time: {end_time_db - start_time_db:.4f} seconds")

    if not user:
        request.session.pop('user_id', None)
        request.session.pop('username', None)
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # --- Construct Dashboard Cards ---
    cards = []

    # Individual cards for each Favorite Spawn
    if user.favourite_spawns:
        for spawn in user.favourite_spawns:
            # For `timedelta` objects (like locking_period), convert to string for simpler display in template
            # If a more complex formatting is needed, create a custom Jinja2 filter or format here.
            cards.append({
                "id": f"favorite-spawn-{spawn.id}", # Unique ID for each spawn card
                "type": "favourite_spawn", # Type for individual spawn cards
                "title": spawn.name, # Title is the spawn name
                "data": { # Pass the full spawn object or a dictionary representation of it
                    "spawn": spawn # Pass the SQLAlchemy object directly, Jinja2 can access its attributes
                }
            })


    breadcrumbs = [
        {'text': 'Dashboard', 'link': None}
    ]

    end_time_total = time.time() # End timing for the entire request
    logger.info(f"Dashboard total request time: {end_time_total - start_time_total:.4f} seconds")

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "current_user": user, # Pass the full user object for layout macro
            "username": username, # Keep for backward compatibility if needed in dashboard.html
            "cards": cards, # Pass the structured cards data
            "breadcrumbs": breadcrumbs
        }
    )

# --- Debug/Test Endpoint (Development Only) ---
if os.environ.get("DEBUG_MODE") == "true":
    import unittest
    import io
    from contextlib import redirect_stdout

    from tests.test_models import TestModels

    @app.get("/debug/tests", response_class=HTMLResponse)
    async def run_unit_tests(request: Request):
        output_buffer = io.StringIO()
        with redirect_stdout(output_buffer):
            suite = unittest.TestSuite()
            suite.addTest(unittest.makeSuite(TestModels))
            runner = unittest.TextTestRunner(stream=output_buffer, verbosity=2)
            runner.run(suite)

        test_results = output_buffer.getvalue()
        return templates.TemplateResponse("test_results.html", {
            "request": request,
            "test_output": test_results
        })
