from utils.api_key_rotate import APIKeyManager
from utils.config import settings

groq_api_manager = APIKeyManager(
    api_keys=settings.groq_api_keys,
    rate_limit=30,
    cooldown_period=60
)

google_api_manager = APIKeyManager(
    api_keys=settings.google_api_keys,
    rate_limit=10,
    cooldown_period=60
)

requesty_api_manager = APIKeyManager(
    api_keys=settings.requesty_api_keys,
    rate_limit=40,
    cooldown_period=60,
)