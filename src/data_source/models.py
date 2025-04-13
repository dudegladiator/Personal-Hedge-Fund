from enum import Enum
from pydantic import BaseModel

class RecommendationSignal(Enum):
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"

class AgentResponse(BaseModel):
    recommendation_signal: RecommendationSignal
    analysis_overview: str
    recommendation_confidence_score: float
    reasoning: str