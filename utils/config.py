import re
from motor.motor_asyncio import AsyncIOMotorClient
# Import Field correctly from pydantic
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings
from pymongo import MongoClient
from dotenv import load_dotenv
from typing import Dict, List, Optional, Tuple # Import Tuple
import os

# Load environment variables
load_dotenv()

class Settings(BaseSettings):
    # Keep your other specific settings
    MONGODB_URI: Optional[str] = os.getenv("MONGODB_URI")
    MONGODB_NAME: Optional[str] = os.getenv("MONGODB_NAME")

    # Use List[str] and default_factory=list
    google_api_keys: List[str] = Field(default_factory=list)
    groq_api_keys: List[str] = Field(default_factory=list)
    requesty_api_keys: List[str] = Field(default_factory=list)

    # --- Use a single model_validator to load all dynamic keys into lists ---
    @model_validator(mode='before')
    @classmethod
    def load_dynamic_api_keys(cls, values: Dict) -> Dict:
        """
        Scans environment variables and loads all matching *_API_KEY<N>
        into sorted lists based on the numeric suffix <N>.
        """
        # Temporary storage for tuples: (number, api_key_value)
        temp_google: List[Tuple[int, str]] = []
        temp_groq: List[Tuple[int, str]] = []
        temp_requesty: List[Tuple[int, str]] = []

        # Compile regex patterns
        google_key_pattern = re.compile(r"GOOGLE_API_KEY(\d+)$")
        groq_key_pattern = re.compile(r"GROQ_API_KEY(\d+)$")
        requesty_key_pattern = re.compile(r"REQUESTY_API_KEY(\d+)$")

        # Scan environment variables once
        for key, value in os.environ.items():
            if not value: # Skip if value is empty
                continue

            # Check Google keys
            match = google_key_pattern.match(key)
            if match:
                try:
                    num = int(match.group(1))
                    temp_google.append((num, value))
                except (ValueError, IndexError):
                    print(f"Warning: Could not parse number from key '{key}'")
                continue # Found a match, move to next env var

            # Check Groq keys
            match = groq_key_pattern.match(key)
            if match:
                try:
                    num = int(match.group(1))
                    temp_groq.append((num, value))
                except (ValueError, IndexError):
                    print(f"Warning: Could not parse number from key '{key}'")
                continue

            # Check Requesty keys
            match = requesty_key_pattern.match(key)
            if match:
                try:
                    num = int(match.group(1))
                    temp_requesty.append((num, value))
                except (ValueError, IndexError):
                    print(f"Warning: Could not parse number from key '{key}'")
                # No continue needed here as it's the last check

        # Sort the temporary lists by the number (the first element of the tuple)
        temp_google.sort(key=lambda item: item[0])
        temp_groq.sort(key=lambda item: item[0])
        temp_requesty.sort(key=lambda item: item[0])

        # Extract the sorted API key values into the final lists
        final_google_keys = [val for num, val in temp_google]
        final_groq_keys = [val for num, val in temp_groq]
        final_requesty_keys = [val for num, val in temp_requesty]

        # Assign the final sorted lists to the values dict Pydantic uses
        # Ensure we don't overwrite existing keys if they were somehow passed in 'values'
        # Although with default_factory=list, they shouldn't pre-exist unless explicitly passed on init.
        values['google_api_keys'] = final_google_keys
        values['groq_api_keys'] = final_groq_keys
        values['requesty_api_keys'] = final_requesty_keys

        return values # Return the modified values dictionary

    class Config:
        extra = 'ignore'


settings = Settings()

# Create database clients using the updated settings
database_client = AsyncIOMotorClient(settings.MONGODB_URI)
database = database_client.get_database(settings.MONGODB_NAME)

pymongo_client = MongoClient(settings.MONGODB_URI)
pymongo_db = pymongo_client.get_database(settings.MONGODB_NAME)

def get_async_database():
    return database

def get_sync_database():
    return pymongo_db