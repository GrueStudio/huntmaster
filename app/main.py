import os
import uuid
from fastapi import FastAPI, Request, Form, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pytz import UTC

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from starlette.middleware.sessions import SessionMiddleware

# Assuming database.py and models.py are in the same 'app' directory
from database import get_db # Import Base and engine for table creation in dev
from models import User, RecoveryToken # Import your User model

# Initialize FastAPI app
app = FastAPI()

app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET_KEY", "a-very-secret-key"))
app.mount("/static", StaticFiles(directory="static"), name="static")

# Configure Jinja2Templates to serve HTML files
# The 'templates' directory should be in the same directory as this main.py file
templates = Jinja2Templates(directory="templates")

# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """
    Root endpoint. Redirects to dashboard if logged in, otherwise to login.
    """
    if 'username' in request.session:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/login", response_class=HTMLResponse)
async def get_login_form(request: Request):
    """
    Displays the login form.
    """

    user_id = request.session.get('user_id')
    if user_id:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login", response_class=HTMLResponse)
async def post_login_form(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Handles the login form submission, authenticates the user, and sets the session.
    """
    user = db.query(User).filter(User.username == username).first()

    if not user or not user.check_password(password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid username or password."})

    # Set session variables upon successful login
    request.session['user_id'] = user.id
    request.session['username'] = user.username

    # Redirect to the dashboard page
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/logout", response_class=HTMLResponse)
async def logout(request: Request):
    """
    Logs out the user by clearing session data and redirects to login.
    """
    request.session.pop('user_id', None)
    request.session.pop('username', None)
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/register", response_class=HTMLResponse)
async def get_register_form(request: Request):
    """
    Displays the user registration form.
    """
    user_id = request.session.get('user_id')
    if user_id:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse("register.html", {"request": request, "error": None})

@app.post("/register", response_class=HTMLResponse)
async def post_register_form(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Handles the submission of the user registration form.
    """
    error_message = None

    # Basic validation
    if not username or not password or not confirm_password:
        error_message = "All fields are required."
    elif password != confirm_password:
        error_message = "Passwords do not match."
    elif len(password) < 6: # Example: minimum password length
        error_message = "Password must be at least 6 characters long."

    if error_message:
        return templates.TemplateResponse("register.html", {"request": request, "error": error_message})

    # Check if username or email already exists
    existing_user = db.query(User).filter(User.username == username).first()

    if existing_user:
        if str(existing_user.username) == username:
            error_message = "Username already registered."
        return templates.TemplateResponse("register.html", {"request": request, "error": error_message})

    try:
        # Create a new user instance
        new_user = User(username=username)
        new_user.set_password(password) # Hash and set password

        db.add(new_user)
        db.commit()
        db.refresh(new_user) # Refresh to get the ID and other default values

        # Redirect to a success page or login page
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER) # Redirect to a login page (you'll create this later)

    except IntegrityError:
        db.rollback()
        error_message = "A user with this username or email already exists."
        return templates.TemplateResponse("register.html", {"request": request, "error": error_message})
    except Exception as e:
        db.rollback()
        print(f"Error during registration: {e}")
        error_message = "An unexpected error occurred during registration."
        return templates.TemplateResponse("register.html", {"request": request, "error": error_message})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """
    Displays the dashboard page. Requires user to be logged in.
    """
    username = request.session.get('username')
    if not username:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("dashboard.html", {"request": request, "username": username})

@app.get("/account-recovery", response_class=HTMLResponse)
async def get_account_recovery(request: Request, db: Session = Depends(get_db)):
    """
    Displays the account recovery page.
    If logged in, shows generated tokens.
    If not logged in, shows form to consume token and reset password.
    """
    user_id = request.session.get('user_id')
    if user_id:
        # User is logged in: show their tokens
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            # Should not happen if session is valid, but handle defensively
            request.session.pop('user_id', None)
            request.session.pop('username', None)
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

        # Fetch active and expired tokens for the user
        tokens = db.query(RecoveryToken).filter(RecoveryToken.user_id == user.id).order_by(RecoveryToken.created_at.desc()).all()

        # Filter out truly expired tokens for display, but keep all for auditing
        active_tokens = [
            token for token in tokens
            if not token.used and token.expiration_time > datetime.now(UTC).replace(tzinfo=None) # Changed 'not token.used' to 'token.used is False'
        ]

        return templates.TemplateResponse(
            "account_recovery.html",
            {"request": request, "logged_in_user": user, "tokens": tokens, "message": None, "error": None}
        )
    else:
        # User is not logged in: show form to consume token
        return templates.TemplateResponse(
            "account_recovery.html",
            {"request": request, "logged_in_user": None, "message": None, "error": None}
        )

@app.post("/account-recovery/generate-token", response_class=HTMLResponse)
async def generate_recovery_token(request: Request, db: Session = Depends(get_db)):
    """
    Generates a new recovery token for the logged-in user.
    """
    user_id = request.session.get('user_id')
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        request.session.pop('user_id', None)
        request.session.pop('username', None)
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # Invalidate old active tokens for this user to prevent clutter and improve security
    db.query(RecoveryToken).filter(
        RecoveryToken.user_id == user.id,
        RecoveryToken.used == False,
        RecoveryToken.expiration_time > datetime.now(UTC).replace(tzinfo=None)
    ).update({"used": True})
    db.commit()

    # Generate a new unique token
    token_value = str(uuid.uuid4())
    # Token valid for 1 hour
    expiration_time = datetime.now(UTC) + timedelta(days=90)

    new_token = RecoveryToken(
        user_id=user.id,
        token=token_value,
        expiration_time=expiration_time,
        used=False
    )
    db.add(new_token)
    db.commit()
    db.refresh(new_token)

    return templates.TemplateResponse(
        "account_recovery.html",
        {"request": request, "logged_in_user": user, "tokens": user.recovery_tokens, "message": "New recovery token generated!", "error": None}
    )

@app.post("/account-recovery", response_class=HTMLResponse)
async def consume_recovery_token(
    request: Request,
    token: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Consumes a recovery token and resets the user's password.
    This route is for unauthenticated users.
    """
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
            {"request": request, "logged_in_user": None, "error": error_message, "message": None}
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
            {"request": request, "logged_in_user": None, "error": error_message, "message": None}
        )

    user = db.query(User).filter(User.id == recovery_token_obj.user_id).first()
    if not user:
        # This case implies data inconsistency, token points to non-existent user
        error_message = "Associated user not found. Invalid token."
        return templates.TemplateResponse(
            "account_recovery.html",
            {"request": request, "logged_in_user": None, "error": error_message, "message": None}
        )

    try:
        user.set_password(new_password)
        recovery_token_obj.used = True # Mark token as used
        db.add(user)
        db.add(recovery_token_obj)
        db.commit()

        # Redirect to login with success message
        return RedirectResponse(
            url="/login?message=Password reset successfully. Please log in.",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except Exception as e:
        db.rollback()
        print(f"Error resetting password: {e}")
        error_message = "An unexpected error occurred during password reset."
        return templates.TemplateResponse(
            "account_recovery.html",
            {"request": request, "logged_in_user": None, "error": error_message, "message": None}
        )



# --- Debug/Test Endpoint (Development Only) ---
# This endpoint will run your unit tests and display a summary.
# It should ONLY be enabled in development containers, not production.
# You can control this with an environment variable, e.g., DEBUG_MODE=true
# For now, it's conditionally included.
if os.environ.get("DEBUG_MODE") == "true":
    import unittest
    import io
    from contextlib import redirect_stdout

    # Import your test suite
    from tests.test_models import TestModels # Assuming tests/test_models.py

    @app.get("/debug/tests", response_class=HTMLResponse)
    async def run_unit_tests(request: Request):
        """
        Runs the unit tests and returns the output.
        This endpoint should ONLY be available in development environments.
        """
        output_buffer = io.StringIO()
        with redirect_stdout(output_buffer):
            # Create a test suite and run it
            suite = unittest.TestSuite()
            suite.addTest(unittest.makeSuite(TestModels))
            runner = unittest.TextTestRunner(stream=output_buffer, verbosity=2)
            runner.run(suite)

        test_results = output_buffer.getvalue()
        return templates.TemplateResponse("test_results.html", {
            "request": request,
            "test_output": test_results
        })
