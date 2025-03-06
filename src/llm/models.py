from langchain_groq import ChatGroq
from langchain_google_genai import GoogleGenerativeAI
from utils.config import settings
from utils.api_key_rotate import APIKeyManager

def get_model(model_name: str):
    if model_name in ["deepseek-r1-distill-llama-70b-specdec", "deepseek-r1-distill-qwen-32b", "llama-3.3-70b-versatile	"]:  # Groq models
        return ChatGroq(model=model_name, api_key=groq_api_manager.use_and_get_key())
    
    elif model_name in ["gemini-2.0-flash", "gemini-2.0-flash-thinking-exp-01-21", "gemini-2.0-pro-exp-02-05"]:  # Google models
        return GoogleGenerativeAI(model=model_name, api_key=google_api_manager.use_and_get_key())
    
    else:
        raise ValueError(f"Unsupported model: {model_name}")
    
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