import json
import re


def parse_sentimental_response(response_content):
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
      
def parse_backtesting_results(response_content):
    """
    Parses the LLM response potentially containing backtesting analysis results.

    Attempts direct JSON parsing first. If that fails, it looks for JSON
    within markdown code blocks (```json ... ```). Also extracts optional
    <think> tags for reasoning.

    Args:
        response_content: The raw string response from the LLM.

    Returns:
        A dictionary containing the parsed backtesting results with an 'error' flag,
        or an error dictionary if parsing fails.
    """
    try:
        # 1. Attempt direct JSON parsing
        try:
            result = json.loads(response_content)
            # --- Validation for Backtesting Structure ---
            if ("executive_summary" in result and
                "detailed_analysis" in result and
                isinstance(result.get("executive_summary"), dict) and
                isinstance(result.get("detailed_analysis"), list) and
                "recommendation_sign" in result["executive_summary"]): # Check a key nested field
                # --- END Validation ---
                result["reasoning"] = "" # Assume no separate reasoning if direct JSON
                result["error"] = False
                return result
            else:
                # Is valid JSON, but doesn't match expected backtesting structure
                # Treat as error for this parser, maybe log or raise specific error later
                 pass # Let it fall through to markdown parsing attempt

        except json.JSONDecodeError:
            # Direct JSON parsing failed, proceed to markdown extraction
            pass

        # 2. Attempt extraction from markdown format
        # Extract thinking/reasoning part (optional, follows pattern of other parser)
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
                # --- Validation for Backtesting Structure ---
                if ("executive_summary" in result and
                    "detailed_analysis" in result and
                    isinstance(result.get("executive_summary"), dict) and
                    isinstance(result.get("detailed_analysis"), list) and
                    "recommendation_sign" in result["executive_summary"]): # Check a key nested field
                    # --- END Validation ---
                    result["reasoning"] = reasoning # Add reasoning if found
                    result["error"] = False
                    return result
                else:
                    # Parsed JSON from markdown, but missing required backtesting keys/structure
                     return {"error": True, "details": "Parsed JSON from markdown missing required backtesting structure"}
            except json.JSONDecodeError:
                # Failed to parse the extracted JSON string
                return {"error": True, "details": "Failed to parse JSON extracted from markdown"}

        # 3. No valid JSON found either directly or in markdown
        return {"error": True, "details": "No valid backtesting JSON found in response (direct or markdown)"}

    except Exception as e:
        # Catch any other unexpected errors during processing
        return {"error": True, "details": f"Unexpected error parsing backtesting response: {str(e)}"}
    
    
    
def parse_fundamental_response(response_content):
    """
    Parses the LLM response potentially containing fundamental analysis results.

    Attempts direct JSON parsing first. If that fails, it looks for JSON
    within markdown code blocks (```json ... ```). Also extracts optional
    <think> tags for reasoning.

    Args:
        response_content: The raw string response from the LLM.

    Returns:
        A dictionary containing the parsed fundamental analysis results with an 'error' flag,
        or an error dictionary if parsing fails.
    """
    try:
        # 1. Attempt direct JSON parsing
        try:
            result = json.loads(response_content)
            # --- Validation for Fundamental Analysis Structure ---
            if ("executive_summary" in result and
                "detailed_analysis" in result and
                isinstance(result.get("executive_summary"), dict) and
                isinstance(result.get("detailed_analysis"), dict) and
                "operating_efficiency" in result["detailed_analysis"] and # Check a key category
                "overall_signal_recommendation" in result["executive_summary"]): # Check a key exec summary field
                # --- END Validation ---
                result["reasoning"] = "" # Assume no separate reasoning if direct JSON
                result["error"] = False
                return result
            else:
                # Is valid JSON, but doesn't match expected fundamental structure
                # Treat as error for this parser, maybe log or raise specific error later
                pass # Let it fall through to markdown parsing attempt

        except json.JSONDecodeError:
            # Direct JSON parsing failed, proceed to markdown extraction
            pass

        # 2. Attempt extraction from markdown format
        # Extract thinking/reasoning part (optional, follows pattern of other parsers)
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
                # --- Validation for Fundamental Analysis Structure ---
                if ("executive_summary" in result and
                    "detailed_analysis" in result and
                    isinstance(result.get("executive_summary"), dict) and
                    isinstance(result.get("detailed_analysis"), dict) and
                    "operating_efficiency" in result["detailed_analysis"] and # Check a key category
                    "overall_signal_recommendation" in result["executive_summary"]): # Check a key exec summary field
                    # --- END Validation ---
                    result["reasoning"] = reasoning # Add reasoning if found
                    result["error"] = False
                    return result
                else:
                    # Parsed JSON from markdown, but missing required fundamental keys/structure
                     return {"error": True, "details": "Parsed JSON from markdown missing required fundamental structure"}
            except json.JSONDecodeError:
                # Failed to parse the extracted JSON string
                return {"error": True, "details": "Failed to parse JSON extracted from markdown"}

        # 3. No valid JSON found either directly or in markdown
        return {"error": True, "details": "No valid fundamental JSON found in response (direct or markdown)"}

    except Exception as e:
        # Catch any other unexpected errors during processing
        return {"error": True, "details": f"Unexpected error parsing fundamental response: {str(e)}"}