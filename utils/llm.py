import json
import re


def parse_llm_response(response_content):
    # Extract thinking/reasoning part
    thinking_pattern = r'<think>(.*?)</think>'
    thinking_match = re.search(thinking_pattern, response_content, re.DOTALL)
    reasoning = thinking_match.group(1).strip() if thinking_match else ""

    # Extract JSON part
    json_pattern = r'```json\s*(\{.*?\})\s*```'
    json_match = re.search(json_pattern, response_content, re.DOTALL)
    
    if json_match:
        json_str = json_match.group(1)
        try:
            result = json.loads(json_str)
            # Verify required keys are present
            if "recommendation_sign" in result and "analysis_overview" in result and "recommendation_confidence_score" in result:
                # Add reasoning to the result
                result["reasoning"] = reasoning
                result["error"] = False
                return result
            else:
                return {
                    "error": True,
                }
        except json.JSONDecodeError:
            return {
                "error": True,
            }
    else:
        return {
            "error": True,
        }