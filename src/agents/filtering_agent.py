import json
import statistics
from typing import Any, Dict, TypedDict, Optional, Tuple
from src.llm.models import get_model
from langgraph.graph import StateGraph, START, END
from utils.app_logger import setup_logger
import math

logger = setup_logger("src/agents/filtering_agent.py")

MODEL_PROVIDER = "GEMINI"
MODEL_NAME = "gemini-2.0-flash"
FORMAT = { "type": "json_object" } # json_object # text

