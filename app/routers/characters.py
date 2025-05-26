import hashlib
import httpx

from fastapi import APIRouter, Request, Form, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import logging



from database import get_db
from models import User, Character, World # Import all necessary models

# Configure Jinja2Templates (assuming templates directory is relative to app root)
templates = Jinja2Templates(directory="templates")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/characters", response_class=HTMLResponse)
async def list_characters(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Displays a list of all characters in the system.
    Requires user to be logged in.
    """
    user_id = request.session.get('user_id')
    if not user_id:
        # Redirect to login if not authenticated
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # Fetch all characters from the database
    characters = db.query(Character).order_by(Character.name).all()

    return templates.TemplateResponse(
        "character_list.html",
        {"request": request, "characters": characters}
    )

@router.post("/characters", response_class=HTMLResponse)
async def create_character(
    request: Request,
    name: str = Form(...), # Only character name is taken from the form
    db: Session = Depends(get_db)
):
    """
    Allows a logged-in user to create a new character.
    Fetches character details (level, vocation, world) from TibiaData.com.
    Generates a validation hash for the character.
    """
    user_id = request.session.get('user_id')
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        request.session.pop('user_id', None)
        request.session.pop('username', None)
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    error_message = None
    tibia_level = None
    tibia_vocation = None
    tibia_world_name = None

    # 1. Check if a VERIFIED character with this name already exists in our DB
    # A character is considered verified if its validation_hash is NULL
    existing_verified_character = db.query(Character).filter(
        Character.name == name,
        Character.validation_hash.is_(None) # Check if it's already verified
    ).first()

    if existing_verified_character:
        error_message = f"Character '{name}' is already verified and owned by another user."
        return RedirectResponse(
            url=f"/characters?error={error_message}",
            status_code=status.HTTP_303_SEE_OTHER
        )

    # 2. Fetch character details from TibiaData.com
    TIBIADATA_CHARACTER_API = f"https://api.tibiadata.com/v4/character/{name}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(TIBIADATA_CHARACTER_API)
            response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
            tibia_data = response.json()

        # Extract character details
        character_info = tibia_data.get('character', {}).get('character', {})
        if not character_info:
            error_message = f"Character '{name}' not found on Tibia.com."
            return RedirectResponse(
                url=f"/characters?error={error_message}",
                status_code=status.HTTP_303_SEE_OTHER
            )

        tibia_level = character_info.get('level')
        tibia_vocation = character_info.get('vocation')
        tibia_world_name = character_info.get('world')

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            error_message = f"Character '{name}' not found on Tibia.com."
        else:
            error_message = f"Error fetching character data from Tibia.com: {e.response.status_code} - {e.response.text}"
        logger.error(f"HTTP error fetching TibiaData: {e}")
        return RedirectResponse(
            url=f"/characters?error={error_message}",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except httpx.RequestError as e:
        error_message = f"Network error connecting to Tibia.com: {e}"
        logger.error(f"Network error fetching TibiaData: {e}")
        return RedirectResponse(
            url=f"/characters?error={error_message}",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except Exception as e:
        error_message = f"An unexpected error occurred while fetching character data: {e}"
        logger.error(f"Error fetching TibiaData: {e}")
        return RedirectResponse(
            url=f"/characters?error={error_message}",
            status_code=status.HTTP_303_SEE_OTHER
        )

    # 3. Find or Create World
    world = db.query(World).filter(World.name == tibia_world_name).first()
    if not world:
        # If world doesn't exist, create it (should ideally be handled by startup script)
        world = World(name=tibia_world_name, location="Unknown") # Default location if not provided by API
        db.add(world)
        db.commit() # Commit world creation immediately to get its ID
        db.refresh(world)
        logger.info(f"Created new world entry: {world.name}")

    # 4. Generate validation hash
    # The hash is MD5(username + character_name).
    # This hash needs to be placed in the character's comment on Tibia.com for validation.
    combined_string = f"{user.username}{name}"
    validation_hash = hashlib.md5(combined_string.encode()).hexdigest()

    # 5. Create or Update Character record in our DB
    # If the character exists but is NOT verified, we can update it.
    existing_character_unverified = db.query(Character).filter(
        Character.name == name,
        Character.validation_hash.isnot(None) # Character exists but is not yet verified
    ).first()

    try:
        if existing_character_unverified:
            # Update existing unverified character
            existing_character_unverified.level = tibia_level
            existing_character_unverified.vocation = tibia_vocation
            existing_character_unverified.world_id = world.id
            existing_character_unverified.user_id = user.id # Assign to current user
            existing_character_unverified.validation_hash = validation_hash # Update hash
            db.add(existing_character_unverified)
            db.commit()
            db.refresh(existing_character_unverified)
            new_character = existing_character_unverified
            message_text = f"Character '{new_character.name}' updated with new validation hash: {validation_hash}. Please place this hash in your Tibia.com character comment to validate."
        else:
            # Create new character
            new_character = Character(
                name=name,
                level=tibia_level,
                vocation=tibia_vocation,
                user_id=user.id,
                world_id=world.id,
                validation_hash=validation_hash # Assign the generated hash
            )
            db.add(new_character)
            db.commit()
            db.refresh(new_character)
            message_text = f"Character '{new_character.name}' added successfully! Your validation hash is: {validation_hash}. Please place this hash in your Tibia.com character comment to validate."

        return RedirectResponse(
            url=f"/characters/{new_character.name}?message={message_text}",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except IntegrityError as e:
        db.rollback()
        error_message = f"A character with the name '{name}' already exists or another database integrity error occurred."
        logger.error(f"Integrity Error during character creation/update: {e}")
    except Exception as e:
        db.rollback()
        error_message = f"An unexpected error occurred during character creation/update: {e}"
        logger.error(f"Error during character creation/update: {e}")

    # If an error occurred, redirect back to the character list page with error message
    return RedirectResponse(
        url=f"/characters?error={error_message}",
        status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/characters/{character_name}", response_class=HTMLResponse)
async def view_character_detail(
    request: Request,
    character_name: str, # This is the path parameter
    db: Session = Depends(get_db)
):
    """
    Displays the detail page for a specific character.
    Requires user to be logged in and own the character.
    """
    username = request.session.get('username')
    user_id = request.session.get('user_id')
    logger.info(f"Viewing character detail for {character_name} by {username}")

    if not username or not user_id:
        # Redirect to login if not authenticated
        logger.info(f"Redirecting {username} to login")
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # Fetch the character by name and ensure it belongs to the logged-in user
    character = db.query(Character).filter(
        Character.name == character_name,
        Character.user_id == user_id
    ).first()

    if not character:
        # If character not found or not owned by user, redirect to my characters with an error
        logger.info(f"Redirecting {username} to my characters with error")
        return RedirectResponse(
            url="/list",
            status_code=status.HTTP_303_SEE_OTHER
        )

    # Get message from query parameters if redirected from character creation
    message = request.query_params.get("message")

    return templates.TemplateResponse(
        "character_details.html",
        {"request": request, "character": character, "message": message}
    )


@router.get("/character/verify", response_class=HTMLResponse)
async def get_verify_character_page(
    request: Request,
    character_name: str, # Expected as a query parameter
    db: Session = Depends(get_db)
):
    """
    Displays the page to verify a character, showing the validation hash
    and a list of other characters on the same account that will be auto-validated.
    """
    logger.info(f"Viewing character verification page for {character_name}")
    user_id = request.session.get('user_id')
    if not user_id:
        logger.info("User not logged in")
        logger.info("Redirecting to login page")
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.info("User not found")
        logger.info("Redirecting to login page")
        request.session.pop('user_id', None)
        request.session.pop('username', None)
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    character_to_verify = db.query(Character).filter(
        Character.user_id == user.id,
        Character.name == character_name,
        Character.validation_hash.isnot(None) # Must be unverified to be on this page
    ).first()

    if not character_to_verify:
        logger.info("Character not found")
        logger.info("Redirecting to list page")
        return RedirectResponse(
            url="/list",
            status_code=status.HTTP_303_SEE_OTHER
        )

    # Fetch other characters from TibiaData.com for the same account
    tibia_other_characters = []
    TIBIADATA_CHARACTER_API = f"https://api.tibiadata.com/v4/character/{character_name}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(TIBIADATA_CHARACTER_API)
            response.raise_for_status()
            tibia_data = response.json()
            tibia_other_characters = tibia_data.get('character', {}).get('other_characters', [])
            logger.info("Fetched other characters from TibiaData")
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching TibiaData for other characters: {e.response.status_code} - {e.response.text}")
        # Continue without other characters if API call fails
    except httpx.RequestError as e:
        logger.error(f"Network error fetching TibiaData for other characters: {e}")
        # Continue without other characters if API call fails
    except Exception as e:
        logger.error(f"An unexpected error occurred fetching TibiaData for other characters: {e}")
        # Continue without other characters if API call fails

    # Filter other characters that belong to the current user and are currently unvalidated
    other_characters_to_validate = []
    for other_char_info in tibia_other_characters:
        other_char_name = other_char_info.get('name')
        if other_char_name == character_name: # Skip the main character itself
            continue
        logger.info(f"Processing other character: {other_char_name}")
        existing_other_char_in_db = db.query(Character).filter(
            Character.name == other_char_name,
            Character.user_id == user.id,
            Character.validation_hash.isnot(None) # Only show if it's currently unvalidated
        ).first()

        if existing_other_char_in_db:
            other_characters_to_validate.append(other_char_name)
        elif not existing_other_char_in_db:
            # If the other character is not in our DB, we can list it as potentially auto-validated
            # since it's on the same account and not yet in our system as validated.
            other_characters_to_validate.append(f"{other_char_name} (New)")


    message = request.query_params.get("message")
    error = request.query_params.get("error")

    return templates.TemplateResponse(
        "character_verify.html",
        {
            "request": request,
            "character": character_to_verify,
            "other_characters_to_validate": other_characters_to_validate,
            "message": message,
            "error": error
        }
    )


@router.post("/character/verify", response_class=HTMLResponse)
async def validate_character(
    request: Request,
    character_name: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Handles the POST request to validate a character.
    Fetches character comment from TibiaData.com and checks for the validation hash.
    If successful, marks the character and other associated characters as validated.
    """
    logger.info(f"Validating character: {character_name}")
    user_id = request.session.get('user_id')
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.info(f"User not found for ID: {user_id}")
        logger.info("Redirecting to login page")
        request.session.pop('user_id', None)
        request.session.pop('username', None)
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    character_to_validate = db.query(Character).filter(
        Character.name == character_name,
        Character.user_id == user.id,
        Character.validation_hash.isnot(None) # Must be unverified to be validated
    ).first()

    if not character_to_validate:
        logger.info("Character not found or already verified.")
        logger.info("Redirecting to characters page")
        return RedirectResponse(
            url="/characters?error=Character not found or already verified.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    expected_hash = character_to_validate.validation_hash
    tibia_character_comment = None
    tibia_other_characters = []

    # Fetch character details from TibiaData.com to get the comment and other characters
    TIBIADATA_CHARACTER_API = f"https://api.tibiadata.com/v4/character/{character_name}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(TIBIADATA_CHARACTER_API)
            response.raise_for_status()
            tibia_data = response.json()

        character_info = tibia_data.get('character', {}).get('character', {})
        tibia_character_comment = character_info.get('comment')
        tibia_other_characters = tibia_data.get('character', {}).get('other_characters', [])

        logger.info("Fetched character details from TibiaData.com")

    except httpx.HTTPStatusError as e:
        error_message = f"Error fetching character data from Tibia.com: {e.response.status_code} - {e.response.text}"
        logger.error(f"HTTP error fetching TibiaData for validation: {e}")
        return RedirectResponse(
            url=f"/character/verify?character_name={character_name}&error={error_message}",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except httpx.RequestError as e:
        error_message = f"Network error connecting to Tibia.com: {e}"
        logger.error(f"Network error fetching TibiaData for validation: {e}")
        return RedirectResponse(
            url=f"/character/verify?character_name={character_name}&error={error_message}",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except Exception as e:
        error_message = f"An unexpected error occurred while fetching character data for validation: {e}"
        logger.error(f"Error fetching TibiaData for validation: {e}")
        return RedirectResponse(
            url=f"/character/verify?character_name={character_name}&error={error_message}",
            status_code=status.HTTP_303_SEE_OTHER
        )

    # Check if the validation hash is present in the Tibia.com character comment
    if not tibia_character_comment or expected_hash not in tibia_character_comment:
        error_message = "Validation hash not found in character comment. Please ensure it's correctly placed on Tibia.com."
        logger.warning(f"Validation hash not found for character {character_name}")
        return RedirectResponse(
            url=f"/character/verify?character_name={character_name}&error={error_message}",
            status_code=status.HTTP_303_SEE_OTHER
        )

    try:
        # Mark the main character as validated
        character_to_validate.validation_hash = None
        db.add(character_to_validate)
        db.flush() # Flush to ensure main character is updated before processing others

        # Auto-validate other characters on the same account
        auto_validated_chars_names = [character_to_validate.name] # Start with the main character
        for other_char_info in tibia_other_characters:
            other_char_name = other_char_info.get('name')
            other_char_world_name = other_char_info.get('world')

            # Skip if it's the main character (already handled)
            if other_char_name == character_to_validate.name:
                continue

            # Find or create world for other character
            other_world = db.query(World).filter(World.name == other_char_world_name).first()
            if not other_world:
                other_world = World(name=other_char_world_name, location="Unknown")
                db.add(other_world)
                db.flush() # Flush to get ID for new world
                logger.info(f"Created new world entry for other character during validation: {other_world.name}")

            # Check if this other character exists in our DB and belongs to the current user and is unvalidated
            existing_other_char_in_db = db.query(Character).filter(
                Character.name == other_char_name,
                Character.user_id == user.id,
                Character.validation_hash.isnot(None) # Only update if it's currently unvalidated
            ).first()

            if existing_other_char_in_db:
                existing_other_char_in_db.validation_hash = None # Mark as validated
                existing_other_char_in_db.world_id = other_world.id # Update world in case it changed
                db.add(existing_other_char_in_db)
                auto_validated_chars_names.append(other_char_name)
            else:
                # If the other character is not in our DB, create it as validated for this user
                new_other_character = Character(
                    name=other_char_name,
                    level=None, # Not available in other_characters list
                    vocation=None, # Not available in other_characters list
                    user_id=user.id,
                    world_id=other_world.id,
                    validation_hash=None, # Automatically validated
                    last_login=None # Not available in other_characters list
                )
                db.add(new_other_character)
                auto_validated_chars_names.append(other_char_name)

        db.commit() # Commit all changes in one transaction

        message_text = f"Character '{character_name}' and associated characters ({', '.join(auto_validated_chars_names)}) have been successfully verified!"
        logger.info(f"Character '{character_name}' and associated characters have been successfully verified.")
        return RedirectResponse(
            url=f"/characters?message={message_text}",
            status_code=status.HTTP_303_SEE_OTHER
        )

    except IntegrityError as e:
        db.rollback()
        error_message = f"Database error during validation: {e}"
        logger.error(f"Integrity Error during character validation: {e}")
    except Exception as e:
        db.rollback()
        error_message = f"An unexpected error occurred during character validation: {e}"
        logger.error(f"Error during character validation: {e}")

    return RedirectResponse(
        url=f"/character/verify?character_name={character_name}&error={error_message}",
        status_code=status.HTTP_303_SEE_OTHER
    )
