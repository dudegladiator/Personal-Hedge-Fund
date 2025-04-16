import json
import re
from typing import Any, Dict


def parse_sentimental_response(response_content, raw_data = None):
    try:
        # First try to parse the response as direct JSON
        try:
            result = json.loads(response_content)
            if "recommendation_sign" in result and "analysis_overview" in result and "recommendation_confidence_score" in result:
                result["reasoning"] = ""  # No reasoning in direct JSON response
                result["error"] = False
                result["raw_data"] = raw_data
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
                        result["raw_data"] = raw_data
                        return result
                except json.JSONDecodeError:
                    return {"error": True, "details": "Failed to parse JSON from markdown", "raw_data": raw_data}
            
            return {"error": True, "details": "No valid JSON found in response", "raw_data": raw_data}
            
    except Exception as e:
        return {"error": True, "details": f"Error parsing response: {str(e)}", "raw_data": raw_data}
      
def parse_backtesting_results(response_content, raw_data = None):
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
                result["raw_data"] = raw_data
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
                    result["raw_data"] = raw_data
                    return result
                else:
                    # Parsed JSON from markdown, but missing required backtesting keys/structure
                     return {"error": True, "details": "Parsed JSON from markdown missing required backtesting structure", "raw_data": raw_data}
            except json.JSONDecodeError:
                # Failed to parse the extracted JSON string
                return {"error": True, "details": "Failed to parse JSON extracted from markdown", "raw_data": raw_data}

        # 3. No valid JSON found either directly or in markdown
        return {"error": True, "details": "No valid backtesting JSON found in response (direct or markdown)", "raw_data": raw_data}

    except Exception as e:
        # Catch any other unexpected errors during processing
        return {"error": True, "details": f"Unexpected error parsing backtesting response: {str(e)}", "raw_data": raw_data}
    
def parse_strategy_code_response(response_content: str) -> Dict[str, Any]:
    """
    Parses the LLM response potentially containing generated strategy code.

    Attempts direct JSON parsing of a list first. If that fails, it looks for
    a JSON list within markdown code blocks (```json ... ```). Also extracts
    optional <think> tags for reasoning.

    Args:
        response_content: The raw string response from the LLM.

    Returns:
        A dictionary containing:
        - 'error' (bool): True if parsing failed, False otherwise.
        - 'strategies' (List[Dict]): The list of parsed strategy objects if successful.
        - 'reasoning' (str): Extracted text from <think> tags, if any.
        - 'details' (str): Error message if 'error' is True.
    """
    output: Dict[str, Any] = {"error": True, "strategies": [], "reasoning": "", "details": ""}

    try:
        # 1. Attempt direct JSON parsing (expecting a list)
        try:
            parsed_data = json.loads(response_content)
            # --- Validation for Strategy Code Structure ---
            if (isinstance(parsed_data, list) and
                all(isinstance(item, dict) and "strategy_name" in item and "strategy_code" in item for item in parsed_data)):
                # --- END Validation ---
                output["strategies"] = parsed_data
                output["error"] = False
                # Assume no separate reasoning if direct JSON list
                return output
            else:
                # Is valid JSON, but not a list of valid strategy objects
                pass # Fall through to markdown parsing attempt

        except json.JSONDecodeError:
            # Direct JSON parsing failed, proceed to markdown extraction
            pass
        except TypeError:
             # Handle cases where parsed_data is not iterable or item is not dict
             pass # Fall through

        # 2. Attempt extraction from markdown format
        # Extract thinking/reasoning part (optional)
        thinking_pattern = r'<think>(.*?)</think>'
        thinking_match = re.search(thinking_pattern, response_content, re.DOTALL)
        reasoning = thinking_match.group(1).strip() if thinking_match else ""
        output["reasoning"] = reasoning # Store reasoning regardless of JSON success

        # Extract JSON part (looking for a list starting with '[')
        json_pattern = r'```json\s*(\[.*?\])\s*```' # Specifically look for a list [...]
        json_match = re.search(json_pattern, response_content, re.DOTALL)

        if json_match:
            json_str = json_match.group(1)
            try:
                parsed_data = json.loads(json_str)
                # --- Validation for Strategy Code Structure ---
                if (isinstance(parsed_data, list) and
                    all(isinstance(item, dict) and "strategy_name" in item and "strategy_code" in item for item in parsed_data)):
                    # --- END Validation ---
                    output["strategies"] = parsed_data
                    output["error"] = False
                    return output
                else:
                    # Parsed JSON list from markdown, but invalid structure/content
                    output["details"] = "Parsed JSON list from markdown missing required strategy structure"
                    return output
            except json.JSONDecodeError:
                # Failed to parse the extracted JSON list string
                output["details"] = "Failed to parse JSON list extracted from markdown"
                return output
            except TypeError:
                 output["details"] = "Error iterating/validating parsed JSON list from markdown"
                 return output

        # 3. No valid JSON list found either directly or in markdown
        output["details"] = "No valid strategy JSON list found in response (direct or markdown)"
        # Check if it might be a single strategy object instead of a list (common LLM mistake)
        json_single_pattern = r'```json\s*(\{.*?\})\s*```'
        json_single_match = re.search(json_single_pattern, response_content, re.DOTALL)
        if json_single_match:
             output["details"] += ". Found a JSON object, but expected a list."

        return output

    except Exception as e:
        # Catch any other unexpected errors during processing
        output["details"] = f"Unexpected error parsing strategy code response: {str(e)}"
        return output
    
def parse_fundamental_response(response_content, raw_data = None):
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
                result["raw_data"] = raw_data
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
                    result["raw_data"] = raw_data
                    return result
                else:
                    # Parsed JSON from markdown, but missing required fundamental keys/structure
                     return {"error": True, "details": "Parsed JSON from markdown missing required fundamental structure", "raw_data": raw_data}
            except json.JSONDecodeError:
                # Failed to parse the extracted JSON string
                return {"error": True, "details": "Failed to parse JSON extracted from markdown", "raw_data": raw_data}

        # 3. No valid JSON found either directly or in markdown
        return {"error": True, "details": "No valid fundamental JSON found in response (direct or markdown)", raw_data: raw_data}

    except Exception as e:
        # Catch any other unexpected errors during processing
        return {"error": True, "details": f"Unexpected error parsing fundamental response: {str(e)}", "raw_data": raw_data}