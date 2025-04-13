import datetime
import bcrypt
from typing import Optional, Dict, Any
from utils.app_logger import setup_logger
from utils.config import get_sync_database

logger = setup_logger("src/routers/auth.py")
db = get_sync_database()

def hash_password(password: str) -> bytes:
    """Hashes a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed_password

def verify_password(stored_hash: bytes, provided_password: str) -> bool:
    """Verifies a provided password against a stored bcrypt hash."""
    return bcrypt.checkpw(provided_password.encode('utf-8'), stored_hash)

def register_user(username: str, password: str) -> bool:
    """
    Registers a new user in the MongoDB database.
    Hashes the password before storing.
    Checks if the username already exists.
    NOTE: This is intended for manual/admin use, not exposed via a public signup endpoint.
    """
    username_lower = username.lower()
    try:
        # Check if user already exists
        existing_user = db.users.find_one({"username": username_lower})
        if existing_user:
            logger.warning(f"Attempted to register existing username: {username_lower}")
            return False # Indicate user already exists

        # Hash the password
        hashed_pw = hash_password(password)

        # Store user data
        user_data = {
            "username": username_lower,
            "hashed_password": hashed_pw,
            "created_at": datetime.datetime.now(datetime.timezone.utc)
        }
        result = db.users.insert_one(user_data)

        if result.inserted_id:
            logger.info(f"Successfully registered user: {username_lower}")
            return True
        else:
            logger.error(f"Failed to insert user data for: {username_lower}")
            return False

    except Exception as e:
        logger.error(f"Error during user registration for {username_lower}: {str(e)}")
        return False

def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    
    username_lower = username.lower()
    try:
        user_data = db.users.find_one({"username": username_lower})

        if not user_data:
            logger.warning(f"Authentication failed: User '{username_lower}' not found.")
            return None

        stored_hash = user_data.get("hashed_password")
        if not stored_hash:
            logger.error(f"Authentication error: User '{username_lower}' has no stored password hash.")
            return None

        if verify_password(stored_hash, password):
            logger.info(f"Authentication successful for user: {username_lower}")
            # Return user data, but exclude the sensitive hash
            user_info = {key: value for key, value in user_data.items() if key != "hashed_password" and key != "_id"}
            user_info["id"] = str(user_data["_id"]) # Optionally include user ID
            return user_info
        else:
            logger.warning(f"Authentication failed: Invalid password for user '{username_lower}'.")
            return None

    except Exception as e:
        logger.error(f"Error during user authentication for {username_lower}: {str(e)}")
        return None
    
    
if __name__ == "__main__":
    print("Auth module loaded. Use register_user() or authenticate_user().")
    # --- Example: Registering a first user ---
    # IMPORTANT: Only run this registration part once or when needed.
    #            Remove or comment out after creating the necessary user(s).
    new_username = "abhijit"
    new_password = "admin" # Change this!
    
    print(f"Attempting to register user: {new_username}")
    success = register_user(new_username, new_password)
    if success:
        print(f"User '{new_username}' registered successfully.")
    else:
        print(f"Failed to register user '{new_username}'. It might already exist or an error occurred.")
    # --- End Example ---

    # --- Example: Testing Authentication ---
    # test_user = "admin"
    # test_pass = "admin" # Use the correct password
    # print(f"\nAttempting to authenticate user: {test_user}")
    # authenticated_user = authenticate_user(test_user, test_pass)
    # if authenticated_user:
    #     print(f"Authentication successful for {test_user}. User data: {authenticated_user}")
    # else:
    #     print(f"Authentication failed for {test_user}.")
    # --- End Example ---