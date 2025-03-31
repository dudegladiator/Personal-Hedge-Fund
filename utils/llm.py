import json
import re


def parse_llm_response(response_content):
    try:
        # First try to parse the response as direct JSON
        try:
            result = json.loads(response_content)
            if "recommendation_sign" in result and "analysis_overview" in result and "recommendation_confidence_score" in result:
                result["reasoning"] = ""  # No reasoning in direct JSON response
                result["error"] = False
                return result
        except json.JSONDecodeError:
            # If direct JSON parsing fails, try extracting from markdown format
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
                        result["reasoning"] = reasoning
                        result["error"] = False
                        return result
                except json.JSONDecodeError:
                    return {"error": True, "details": "Failed to parse JSON from markdown"}
            
            return {"error": True, "details": "No valid JSON found in response"}
            
    except Exception as e:
        return {"error": True, "details": f"Error parsing response: {str(e)}"}