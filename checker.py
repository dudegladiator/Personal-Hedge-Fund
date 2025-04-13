import os
import asyncio
import openai
import time
from utils.config import settings

ROUTER_API_KEY = settings.requesty_api_keys[0] if settings.requesty_api_keys else None

if ROUTER_API_KEY is None:
    raise ValueError("ROUTER_API_KEY not found. Please check your .env file.")

# --- Configuration ---
NUM_CALLS = 100
MODEL_NAME = "google/gemini-2.0-flash-thinking-exp-01-21" # Or your desired model
PROMPT = "Hello, who are you?"
RATE_LIMIT_ERROR_INDICATOR = "RATE_LIMIT_429_ERROR"

# Initialize Async OpenAI client (use AsyncOpenAI)
async_client = openai.AsyncOpenAI(
    api_key=ROUTER_API_KEY,
    base_url="https://router.requesty.ai/v1",
    # Note: Authorization header is often handled automatically by the library
    # when api_key is provided, but explicitly adding it can be okay if needed.
    default_headers={"Authorization": f"Bearer {ROUTER_API_KEY}"} # Usually not needed here
)

async def make_api_call(call_number: int):
    """Makes a single async API call and returns the result, an error message,
       or a specific indicator for rate limit errors."""
    try:
        # print(f"Starting call {call_number}...") # Optional: can make output noisy
        response = await async_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": f"{PROMPT} (Request #{call_number})"}],
            timeout=30 # Add a reasonable timeout
        )

        if response.choices:
            content = response.choices[0].message.content
            print(content)
            return f"Call {call_number} Result: {content}"
        else:
            print(f"Call {call_number} returned no choices.")
            return f"Call {call_number} Error: No response choices found."

    except openai.APIError as e:
        # Check specifically for the 429 Rate Limit error
        if hasattr(e, 'status_code') and e.status_code == 429:
            print(f"Call {call_number} hit Rate Limit (429). Error: {e}")
            return RATE_LIMIT_ERROR_INDICATOR # Return the special indicator
        else:
            # Handle other API errors (e.g., server errors 5xx)
            print(f"Call {call_number} failed with API error (Code: {getattr(e, 'status_code', 'N/A')}): {e}")
            return f"Call {call_number} API Error: {e}"
    except Exception as e:
        # Handle other unexpected errors (e.g., network issues before API call)
        print(f"Call {call_number} failed with unexpected error: {e}")
        return f"Call {call_number} Unexpected Error: {e}"

async def main():
    """Creates and runs multiple API call tasks concurrently and counts 429 errors."""
    print(f"--- Starting {NUM_CALLS} async API calls to {MODEL_NAME} via Requesty ---")
    start_time = time.time()

    tasks = [make_api_call(i + 1) for i in range(NUM_CALLS)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    end_time = time.time()
    print(f"--- Finished {NUM_CALLS} calls in {end_time - start_time:.2f} seconds ---")

    # --- Analysis ---
    successful_calls = 0
    rate_limit_errors = 0
    other_errors = 0

    print("\n--- Call Results Summary ---")
    for i, result in enumerate(results):
        call_num = i + 1
        if isinstance(result, Exception):
            # Handle exceptions potentially raised *before* gather returned them
            print(f"Task {call_num}: Raised an exception directly: {result}")
            other_errors += 1
        elif result == RATE_LIMIT_ERROR_INDICATOR:
            # Already printed details in make_api_call
            rate_limit_errors += 1
        elif isinstance(result, str) and ("Error:" in result or "Failed:" in result):
             # Catch errors returned as strings from make_api_call that weren't 429
             # (The print happened within make_api_call already)
            other_errors += 1
        else:
            # Assume successful if none of the above
            successful_calls += 1
            # Optionally print success results here if needed
            # print(result) # Can be very verbose

    print("\n--- Final Count ---")
    print(f"Successful calls:     {successful_calls}")
    print(f"Rate limit errors (429):{rate_limit_errors}")
    print(f"Other errors:         {other_errors}")
    print(f"Total attempts:       {len(results)}") # Should equal NUM_CALLS

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"An error occurred running the async main function: {e}")