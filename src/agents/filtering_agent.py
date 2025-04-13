import json
import statistics
from typing import Any, Dict, TypedDict, Optional, Tuple
from src.data_source.apis_2 import get_overall_fundamental_data
from src.llm.models import get_model
from langgraph.graph import StateGraph, START, END
from utils.app_logger import setup_logger
from src.prompts import fundamental_agent_system_prompt
import math
from utils.llm import parse_fundamental_response

logger = setup_logger("src/agents/filtering_agent.py")

MODEL_PROVIDER = "GEMINI"
MODEL_NAME = "gemini-2.0-flash"
FORMAT = { "type": "json_object" } # json_object # text