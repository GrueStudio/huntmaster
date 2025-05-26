from datetime import datetime, timedelta, UTC
import uuid

from fastapi import APIRouter, Request, Form, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database import get_db
from models import User, RecoveryToken

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure Jinja2Templates (assuming templates directory is relative to app root)
templates = Jinja2Templates(directory="templates")

router = APIRouter()

# Helper function for current UTC naive time (used in templates)
def get_now_utc_naive():
    return datetime.now(UTC).replace(tzinfo=None)

@router.get("/login", response_class=HTMLResponse)
async def get_login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@router.post("/login", response_class=HTMLResponse)
async def post_login_form(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == username).first()

    if not user or not user.check_password(password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid username or password."})

    request.session['user_id'] = user.id
    request.session['username'] = user.username

    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/logout", response_class=HTMLResponse)
async def logout(request: Request):
    request.session.pop('user_id', None)
    request.session.pop('username', None)
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/register", response_class=HTMLResponse)
async def get_register_form(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": None})

@router.post("/register", response_class=HTMLResponse)
async def post_register_form(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    error_message = None

    if not username or not email or not password or not confirm_password:
        error_message = "All fields are required."
    elif password != confirm_password:
        error_message = "Passwords do not match."
    elif len(password) < 6:
        error_message = "Password must be at least 6 characters long."

    if error_message:
        return templates.TemplateResponse("register.html", {"request": request, "error": error_message})

    existing_user_by_username = db.query(User).filter(User.username == username).first()
    if existing_user_by_username:
        error_message = "Username already registered."
        return templates.TemplateResponse("register.html", {"request": request, "error": error_message})

    try:
        new_user = User(username=username)
        new_user.set_password(password)

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    except IntegrityError:
        db.rollback()
        error_message = "A user with this username or email already exists (database integrity error)."
        return templates.TemplateResponse("register.html", {"request": request, "error": error_message})
    except Exception as e:
        db.rollback()
        logger.error(f"Error during registration: {e}")
        error_message = "An unexpected error occurred during registration."
        return templates.TemplateResponse("register.html", {"request": request, "error": error_message})

@router.get("/account-recovery", response_class=HTMLResponse)
async def get_account_recovery(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get('user_id')
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            request.session.pop('user_id', None)
            request.session.pop('username', None)
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

        # Fetch characters for the logged-in user
        # Note: Character import will be moved to characters.py router
        # For now, we need it here to pass to the template
        from models import Character, World # Temporary import for this template context
        characters = db.query(Character).filter(Character.user_id == user.id).order_by(Character.name).all()
        worlds = db.query(World).order_by(World.name).all()

        return templates.TemplateResponse(
            "account_recovery.html",
            {"request": request, "logged_in_user": user, "characters": characters, "worlds": worlds, "message": None, "error": None, "now_utc_naive": get_now_utc_naive()}
        )
    else:
        return templates.TemplateResponse(
            "account_recovery.html",
            {"request": request, "logged_in_user": None, "message": None, "error": None, "now_utc_naive": get_now_utc_naive()}
        )

@router.post("/account-recovery/generate-token", response_class=HTMLResponse)
async def generate_recovery_token(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get('user_id')
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        request.session.pop('user_id', None)
        request.session.pop('username', None)
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # Invalidate old active tokens for this user
    db.query(RecoveryToken).filter(
        RecoveryToken.user_id == user.id,
        RecoveryToken.used == False,
        RecoveryToken.expiration_time > datetime.now(UTC).replace(tzinfo=None)
    ).update({"used": True})
    db.commit()

    db.refresh(user)

    token_value = str(uuid.uuid4())
    expiration_time = datetime.now(UTC) + timedelta(hours=1)

    new_token = RecoveryToken(
        user_id=user.id,
        token=token_value,
        expiration_time=expiration_time,
        used=False
    )
    db.add(new_token)
    db.commit()
    db.refresh(new_token)

    return RedirectResponse(url="/account-recovery", status_code=status.HTTP_303_SEE_OTHER)

@router.post(
    "/account-recovery",
    response_class=HTMLResponse,
    # dependencies=[Depends(RateLimiter(times=5, seconds=60))] # Limit to 5 attempts per minute per IP
)
async def consume_recovery_token(
    request: Request,
    token: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    error_message = None

    if not token or not new_password or not confirm_password:
        error_message = "All fields are required."
    elif new_password != confirm_password:
        error_message = "New passwords do not match."
    elif len(new_password) < 6:
        error_message = "New password must be at least 6 characters long."

    if error_message:
        return templates.TemplateResponse(
            "account_recovery.html",
            {"request": request, "logged_in_user": None, "error": error_message, "message": None, "now_utc_naive": get_now_utc_naive()}
        )

    recovery_token_obj = db.query(RecoveryToken).filter(RecoveryToken.token == token).first()

    if not recovery_token_obj:
        error_message = "Invalid or expired token."
    elif recovery_token_obj.used:
        error_message = "Token has already been used."
    elif recovery_token_obj.expiration_time < datetime.now(UTC).replace(tzinfo=None):
        error_message = "Token has expired."

    if error_message:
        return templates.TemplateResponse(
            "account_recovery.html",
            {"request": request, "logged_in_user": None, "error": error_message, "message": None, "now_utc_naive": get_now_utc_naive()}
        )

    user = db.query(User).filter(User.id == recovery_token_obj.user_id).first()
    if not user:
        error_message = "Associated user not found. Invalid token."
        return templates.TemplateResponse(
            "account_recovery.html",
            {"request": request, "logged_in_user": None, "error": error_message, "message": None, "now_utc_naive": get_now_utc_naive()}
        )

    try:
        user.set_password(new_password)
        recovery_token_obj.used = True
        db.add(user)
        db.add(recovery_token_obj)
        db.commit()

        return RedirectResponse(
            url="/login?message=Password reset successfully. Please log in.",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error resetting password: {e}")
        error_message = "An unexpected error occurred during password reset."
        return templates.TemplateResponse(
            "account_recovery.html",
            {"request": request, "logged_in_user": None, "error": error_message, "message": None, "now_utc_naive": get_now_utc_naive()}
        )
