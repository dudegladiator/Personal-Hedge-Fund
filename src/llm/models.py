from groq import Groq
from langchain_google_genai import GoogleGenerativeAI
from utils.config import settings
from utils.api_key_rotate import APIKeyManager

def get_model(model_provider: str  = "GROQ"):
    if model_provider in ["GROQ"]:  # Groq models
        return Groq(api_key=groq_api_manager.use_and_get_key())
    
    elif model_provider in ["GEMINI"]:  # Google models
        return GoogleGenerativeAI(model=model_provider, api_key=google_api_manager.use_and_get_key())
    
    else:
        raise ValueError(f"Unsupported model: {model_provider}")
    
groq_api_manager = APIKeyManager(
    api_keys=[settings.GROQ_API_KEY1, settings.GROQ_API_KEY2],
    rate_limit=30,
    cooldown_period=60
)

google_api_manager = APIKeyManager(
    api_keys=[settings.GOOGLE_API_KEY1, settings.GOOGLE_API_KEY2],
    rate_limit=10,
    cooldown_period=60
)