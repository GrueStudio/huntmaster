import os
from datetime import datetime, UTC
import httpx # Import httpx for making async HTTP requests

from fastapi import FastAPI, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

# Assuming database.py and models.py are in the same 'app' directory
from database import get_db, engine
from models import Base, World # Only import models directly used here
from routers import accounts, characters # Import the new routers

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI()

# Add SessionMiddleware for session management
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET_KEY", "a-very-secret-key"))

# Mount the static directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Configure Jinja2Templates (assuming templates directory is relative to app root)
templates = Jinja2Templates(directory="templates")

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

# --- Main Routes ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    if 'username' in request.session:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    username = request.session.get('username')
    if not username:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("dashboard.html", {"request": request, "username": username})


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
