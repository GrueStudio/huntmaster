import hashlib
import httpx
from json import JSONDecodeError

from fastapi import APIRouter, Request, Form, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import and_
import logging



from database import get_db
from models import User, Character, World # Import all necessary models

from templating import templates

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
    characters = db.query(Character).filter(Character.user_id == user_id).order_by(Character.name).all()

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

    # 2. Fetch character details from TibiaData.com
    character_data, error = await get_character_data(name)
    if not character_data:
        return RedirectResponse(url=f"/characters?error={error}", status_code=status.HTTP_303_SEE_OTHER)


    # 3. Find or Create World
    world = db.query(World).filter(World.name == character_data['world']).first()
    if not world:
        # If world doesn't exist, create it (should ideally be handled by startup script)
        world = World(name=character_data['world'], location="Unknown") # Default location if not provided by API
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

    try:
        # Create new character
        new_character = Character(
            name=name,
            level=character_data['level'],
            vocation=character_data['vocation'],
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

    # get and update character data
    character_data, other_characters = await get_character_data(character_name)
    if not character_data:
        error_message = f"Character '{character_name}' not found."
        return RedirectResponse(
            url=f"/characters?error={error_message}",
            status_code=status.HTTP_303_SEE_OTHER
        )
    db.query(Character).filter(Character.name == character_name).update({"level": character_data['level']})
    challenges = db.query(Character).filter(Character.name == character_name, Character.validation_hash != None).count()

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
        { "request": request, "character": character, "message": message, 'challenges': challenges }
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
        other_char_name = other_char_info['name']
        if other_char_name == character_name or other_char_info['world'] != character_to_verify.world.name: # Skip the main character itself
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

def validated_characters_on_world(other_chars_list : list,world_name: int, db : Session):
    logger.info(f"Other characters on world: {other_chars_list}")
    names_list = [char["name"] for char in other_chars_list if char["world"] == world_name]
    validated_in_database = db.query(Character.name).filter(
            Character.validation_hash == None,
            Character.name.in_(names_list)
        ).all()
    validated_names = [name[0] for name in validated_in_database]
    return [name for name in names_list if name != "" and name not in validated_names]

def verify_character(user : User, world : World, character_data : dict, db : Session):
    character_name = character_data["name"]
    character_level = character_data["level"]
    character_vocation = character_data["vocation"]

    character_in_db = db.query(Character).filter(
            and_(Character.name == character_name, Character.user_id == user.id)
        ).first()
    other_verified_claims = db.query(Character).filter(
        Character.name == character_name,
        Character.validation_hash == None,
        Character.user_id != user.id
    ).all()
    if character_in_db and not character_in_db.validated:
        character_in_db.validation_hash = None
        db.commit()
        db.refresh(character_in_db)
    elif not character_in_db:
        character_in_db = Character(name=character_name, world=world, level=character_level, vocation=character_vocation, user_id=user.id, validation_hash=None)
        db.add(character_in_db)
        db.commit()
        db.refresh(character_in_db)

    if len(other_verified_claims) > 0:
        for other_claim in other_verified_claims:
            db.delete(other_claim)
            db.commit()
            db.refresh(other_claim)
    return character_in_db

async def get_character_data(character_name: str):
    """
    Fetches character data from the TibiaData API.

    Args:
        character_name (str): The name of the Tibia character to search for.

    Returns:
        dict | None: A dictionary containing the character data if successful,
                     otherwise None.
    """
    BASE_URL = "https://api.tibiadata.com/v4"
    endpoint = f"/character/{character_name.replace(' ', '%20')}" # Replace spaces for URL
    url = f"{BASE_URL}{endpoint}"

    print(f"Attempting to fetch data for character: {character_name}")
    print(f"API URL: {url}")

    try:
        # Use httpx.AsyncClient for asynchronous requests
        async with httpx.AsyncClient() as client:
            response = await client.get(url, follow_redirects=True, timeout=10.0)
            response.raise_for_status()  # Raise an exception for 4xx or 5xx responses

            # Parse the JSON response
            data = response.json()

            # TibiaData API often wraps actual data in 'characters' -> 'character'
            if data and 'character' in data and 'character' in data['character']:
                character_info = data['character']['character']
                other_characters = data['character']['other_characters']
                return character_info, other_characters
            elif data and 'error' in data:
                logger.error(f"API Error for {character_name}: {data['error']['message']}")
                return None, data['error']['message']
            else:
                logger.warning(f"Unexpected response format for {character_name}: {data}")
                return None, f"Unexpected response format for {character_name}: {data}"

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error occurred for {character_name}: {e.response.status_code} - {e.response.text}")
        if e.response.status_code == 404:
            logger.warning(f"Character '{character_name}' not found.")
        return None, e.response.text
    except httpx.RequestError as e:
        logger.error(f"An error occurred while requesting {e.request.url!r}: {e}")
        return None, f"An error occurred while requesting {e.request.url!r}: {e}"
    except JSONDecodeError as e:
        logger.error(f"Failed to decode JSON from response for {character_name}.")
        return None, str(e)
    except Exception as e:
        logger.error(f"An unexpected error occurred for {character_name}: {e}")
        return None, str(e)


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
    user_id = request.session.get('user_id')
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        return RedirectResponse(url="/login")

    # Verify Main Character
    character_data, other_characters = await get_character_data(character_name)

    if not character_data:
        return RedirectResponse(
            url=f"/character/verify?character_name={character_name}&error={other_characters}",
            status_code=status.HTTP_303_SEE_OTHER
        )
    world = db.query(World).filter(World.name == character_data['world']).first()
    character = verify_character(user, world, character_data, db)

    if not character:
        return RedirectResponse(
            url=f"/character/verify?character_name={character_name}&error=an error happened verifying {character_name}",
            status_code=status.HTTP_303_SEE_OTHER
        )

    if other_characters and len(other_characters) > 0:
        logger.info(f"Processing {other_characters}")
        other_char_data = None
        for other_char_name in validated_characters_on_world(other_characters, character_data['world'], db):
            other_char_data, _ = await get_character_data(other_char_name)
            if not other_char_data:
                logger.error(f"Failed to fetch data for character {other_char_name}")
                continue
            other_char_db = verify_character(user, world, other_char_data, db)
            if not other_char_db:
                logger.error(f"Failed to verify character {other_char_name}")
                return RedirectResponse(
                    url=f"/character/verify?character_name={character_name}&error=an error happened verifying {other_char_name}",
                    status_code=status.HTTP_303_SEE_OTHER
                )

    return RedirectResponse(url="/characters", status_code=status.HTTP_303_SEE_OTHER)



@router.get("/character/disown", response_class=HTMLResponse)
async def get_disown_character_page(
    request: Request,
    character_name: str, # Expected as a query parameter
    db: Session = Depends(get_db)
):
    """
    Displays a confirmation page to disown a character, showing its stats.
    """
    user_id = request.session.get('user_id')
    if not user_id:
        logger.info(f"Unauthorized access to disown confirmation page for {character_name}, redirecting to login.")
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.error(f"User ID {user_id} not found in DB during disown confirmation page access. Session may be stale.")
        request.session.pop('user_id', None)
        request.session.pop('username', None)
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    character_to_disown = db.query(Character).filter(
        Character.name == character_name,
        Character.user_id == user.id, # Must be owned by the current user
    ).first()

    if not character_to_disown:
        logger.warning(f"User {user.username} attempted to access disown page for non-existent, or unowned: {character_name}")
        return RedirectResponse(
            url="/characters?error=Character not found, or not owned by you.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    message = request.query_params.get("message")
    error = request.query_params.get("error")

    logger.info(f"User {user.username} accessing disown confirmation page for {character_name}.")
    return templates.TemplateResponse(
        "character_disown_confirm.html",
        {
            "request": request,
            "character": character_to_disown,
            "message": message,
            "error": error
        }
    )


@router.post("/character/disown", response_class=HTMLResponse)
async def disown_character(
    request: Request,
    character_name: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Allows a logged-in user to disown a character they currently own.
    Sets user_id to None and validation_hash to None.
    """
    user_id = request.session.get('user_id')
    if not user_id:
        logger.warning("Attempt to disown character by unauthenticated user.")
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.error(f"User ID {user_id} not found in DB during disown. Session may be stale.")
        request.session.pop('user_id', None)
        request.session.pop('username', None)
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    character_to_disown = db.query(Character).filter(
        Character.name == character_name,
        Character.user_id == user.id, # Must be owned by the current user
    ).first()

    if not character_to_disown:
        logger.warning(f"User {user.username} attempted to disown non-existent, or unowned: {character_name}")
        return RedirectResponse(
            url=f"/characters?error=Character not found, or not owned by you.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    try:
        db.delete(character_to_disown)
        db.commit()
        logger.info(f"User {user.username} successfully disowned character: {character_name}")
        return RedirectResponse(
            url=f"/characters?message=Character '{character_name}' has been successfully disowned.",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except Exception as e:
        db.rollback()
        error_message = f"An unexpected error occurred while disowning character: {e}"
        logger.error(f"Error disowning character {character_name} for user {user.username}: {e}", exc_info=True)
        return RedirectResponse(
            url=f"/characters/disown?character_name={character_name}&error={error_message}", # Redirect back to confirm page on error
            status_code=status.HTTP_303_SEE_OTHER
        )
