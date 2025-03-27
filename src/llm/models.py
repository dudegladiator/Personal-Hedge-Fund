from langsmith.wrappers import wrap_openai
from openai import OpenAI
from utils.runner import groq_api_manager, google_api_manager

def get_model(model_provider: str  = "GROQ"):
    if model_provider in ["GROQ"]:  # Groq models
        groq_client=OpenAI(
            api_key=groq_api_manager.use_and_get_key(),
            base_url="https://api.groq.com/openai/v1",
        )
        return wrap_openai(groq_client)
    
    elif model_provider in ["GEMINI"]:
        google_client = OpenAI(
            api_key=google_api_manager.use_and_get_key(),
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        return wrap_openai(google_client)
    
    else:
        raise ValueError(f"Unsupported model: {model_provider}")