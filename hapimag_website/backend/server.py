from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timedelta
from pathlib import Path
import json
import os
import re
import urllib.error
import urllib.request


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
DATA_PATH = Path(__file__).with_name("destinations.json")
COORDS_PATH = Path(__file__).with_name("destination_coords.json")
PROMPT_PATH = Path(__file__).parent / "prompts" / "trip_search_prompt.txt"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def load_env_file(path):
    """Load simple KEY=value lines from a local .env file.

    Why: it lets you keep GEMINI_API_KEY in the project root instead of typing
    it into PowerShell every time.
    How: we read each non-empty line, skip comments, split on the first equals
    sign, and add the value to os.environ only if it is not already set.
    """
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key:
            os.environ[key] = value


load_env_file(ENV_PATH)

DESTINATIONS = json.loads(DATA_PATH.read_text(encoding="utf-8"))
DESTINATION_COORDS = json.loads(COORDS_PATH.read_text(encoding="utf-8"))
PROMPT_TEMPLATE = PROMPT_PATH.read_text(encoding="utf-8")
GEMINI_MODEL = os.getenv("GEMINI_MODEL")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEBUG_GEMINI = os.getenv("DEBUG_GEMINI", "true").lower() not in {"0", "false", "no", "off"}
DEBUG_GEMINI_VERBOSE = os.getenv("DEBUG_GEMINI_VERBOSE", "").lower() in {"1", "true", "yes", "on"}
GEMINI_LOG_PATH = Path(__file__).with_name("gemini_debug.log")
CURRENT_YEAR = datetime.now().year

# These groups give the backend a simple shared vocabulary.
# When a user says "beach" or "bike" or "city", we map that language to a
# smaller set of tags that match the destinations in our local data file.
TAG_SYNONYMS = {
    "Beach": ["beach", "sea", "seaside", "ocean", "coast", "coastal", "swim", "swimming"],
    "Biking": ["bike", "biking", "bicycle", "cycling", "cycle", "mountain biking"],
    "Hiking": ["hike", "hiking", "walk", "walking", "trail", "trekking"],
    "Skiing": ["ski", "skiing", "snow", "winter"],
    "Wellness": ["wellness", "spa", "relax", "relaxing", "massage", "sauna"],
    "Family friendly": ["family", "kids", "children", "child friendly"],
    "Pure nature": ["nature", "mountains", "countryside", "forest", "lake", "outdoor"],
    "Culture & heritage": ["culture", "heritage", "museum", "museums", "history", "historic"],
    "City trip": ["city", "cities", "shopping", "urban"],
    "Golf": ["golf", "golfing"],
    "Tennis": ["tennis"],
    "Water sports": ["water sport", "water sports", "sailing", "snorkeling", "windsurfing"],
}

# These are tiny helper patterns for common trip length phrases.
# We turn words like "one week" into a number so the model and fallback logic
# can reason about trip length in a consistent way.
DURATION_PATTERNS = [
    (r"\bone week\b|\b1 week\b|\bseven days\b|\b7 days\b", 7),
    (r"\btwo weeks\b|\b2 weeks\b|\bfourteen days\b|\b14 days\b", 14),
    (r"\bweekend\b", 3),
]

# These are the date phrases we understand out of the box.
# They let us spot things like "early june" or "late august" and pass that
# information through to the LLM or use it in fallback logic.
DATE_WINDOWS = [
    "early january", "mid january", "late january",
    "early february", "mid february", "late february",
    "early march", "mid march", "late march",
    "early april", "mid april", "late april",
    "early may", "mid may", "late may",
    "early june", "mid june", "late june",
    "early july", "mid july", "late july",
    "early august", "mid august", "late august",
    "early september", "mid september", "late september",
    "early october", "mid october", "late october",
    "early november", "mid november", "late november",
    "early december", "mid december", "late december",
]

# Region phrases we should treat as hard location requirements.
# If the user asks for one of these regions and our catalog has no destination
# there, we return no results instead of showing unrelated "close enough" trips.
UNSUPPORTED_REGION_PATTERNS = {
    "South East Asia": [
        r"\bsouth\s*east\s*asia\b",
        r"\bsoutheast\s*asia\b",
        r"\bthailand\b",
        r"\bvietnam\b",
        r"\bindonesia\b",
        r"\bmalaysia\b",
        r"\bphilippines\b",
        r"\bcambodia\b",
        r"\blaos\b",
        r"\bsingapore\b",
    ],
}


def normalize(text):
    """Make text easier to compare by lowercasing it and trimming extra spaces.

    Why: user input can arrive in many shapes, like uppercase, mixed case,
    or with weird spacing.
    How: we lower the string and collapse repeated spaces into one.
    """
    return re.sub(r"\s+", " ", text.lower()).strip()


def log_gemini(message, payload=None, verbose_only=False):
    """Print Gemini debug logs when enabled in `.env`.

    Why: it helps you see whether Gemini is called, what model is used, and
    what kind of response came back.
    How: set DEBUG_GEMINI=true for safe logs. Set DEBUG_GEMINI_VERBOSE=true
    only when you also want to print larger request/response payloads.
    """
    if not DEBUG_GEMINI:
        return

    if verbose_only and not DEBUG_GEMINI_VERBOSE:
        return

    lines = [f"[gemini] {message}"]
    if payload is not None:
        lines.append(json.dumps(payload, ensure_ascii=False, indent=2))

    output = "\n".join(lines)
    print(output, flush=True)
    with GEMINI_LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(output + "\n")


def parse_trip_request(query):
    """Turn a user sentence into a small set of basic search hints.

    Why: if the LLM is unavailable, this gives us a dependable fallback.
    How: we scan the text for known tags, countries, trip length, and date
    phrases, then return them in one simple JSON-like dictionary.
    """
    text = normalize(query)
    tags = []
    countries = []
    duration_days = None
    date_window = None
    budget = None

    for tag, words in TAG_SYNONYMS.items():
        if any(word in text for word in words):
            tags.append(tag)

    for country in sorted({item["country"] for item in DESTINATIONS}):
        if country.lower() in text:
            countries.append(country)

    for pattern, days in DURATION_PATTERNS:
        if re.search(pattern, text):
            duration_days = days
            break

    budget_match = re.search(r"(\d+)\s*points", text)
    if budget_match:
        budget = int(budget_match.group(1))

    for window in DATE_WINDOWS:
        if window in text:
            date_window = window.title()
            break

    if not date_window:
        for month in [
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
        ]:
            if month in text:
                date_window = month.title()
                break

    return {
        "query": query,
        "tags": tags,
        "countries": countries,
        "duration_days": duration_days,
        "date_window": date_window,
        "budget": budget,
        "semantic_intent": [],
        "used_llm": False,
    }


def requested_unsupported_regions(query, criteria=None):
    """Find requested regions that our destination catalog does not cover.

    Why: "best biking in South East Asia" should not return Europe just
    because Europe has biking destinations.
    How: we check the raw user query and the LLM's semantic intent for known
    unsupported region phrases.
    """
    text_parts = [query]
    if criteria:
        text_parts.extend(criteria.get("semantic_intent", []))
        text_parts.extend(criteria.get("countries", []))

    text = normalize(" ".join(text_parts))
    matches = []

    for region, patterns in UNSUPPORTED_REGION_PATTERNS.items():
        if any(re.search(pattern, text) for pattern in patterns):
            matches.append(region)

    return matches


def build_destination_catalog():
    """Create a compact destination list for the prompt.

    Why: the LLM should know what destinations actually exist in our app.
    How: we strip each destination down to the fields the model needs for
    reasoning, then turn the list into formatted JSON text.
    """
    rows = []
    for item in DESTINATIONS:
        rows.append({
            "id": item["id"],
            "name": item["name"],
            "location": item["location"],
            "country": item["country"],
            "tags": item["tags"],
            "description": item["description"],
        })
    return json.dumps(rows, ensure_ascii=False, indent=2)


def build_llm_schema():
    """Describe the exact JSON shape we want back from Gemini.

    Why: this makes the model reply in a machine-friendly format instead of
    free-form prose.
    How: we define the keys, types, and required fields for the response.
    """
    return {
        "type": "object",
        "properties": {
            "criteria": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "countries": {"type": "array", "items": {"type": "string"}},
                    "duration_days": {"type": "integer", "nullable": True},
                    "date_window": {"type": "string", "nullable": True},
                    "budget": {"type": "integer", "nullable": True},
                    "semantic_intent": {"type": "array", "items": {"type": "string"}},
                    "used_llm": {"type": "boolean"},
                },
                "required": [
                    "query",
                    "tags",
                    "countries",
                    "duration_days",
                    "date_window",
                    "semantic_intent",
                    "used_llm",
                ],
            },
            "recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "score": {"type": "integer"},
                        "reasons": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["id", "score", "reasons"],
                },
            },
            "alternative_recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "score": {"type": "integer"},
                        "reasons": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["id", "score", "reasons"],
                },
            },
            "recommendation_text": {"type": "string"},
        },
        "required": ["criteria", "recommendations", "alternative_recommendations", "recommendation_text"],
    }


def build_weather_tool():
    """Build the Gemini function-calling tool declaration for weather.

    Why: this lets Gemini decide when to fetch weather for recommended
    destinations, based on whether the user mentioned specific dates.
    How: we declare a single function the model can call zero or more times.
    """
    return {
        "function_declarations": [
            {
                "name": "get_weather_forecast",
                "description": (
                    "Get the daily weather forecast for a specific Hapimag destination "
                    "during a date range. Call this for each recommended destination "
                    "when the user specifies travel dates. Only works for dates within "
                    "the next 16 days."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "destination_id": {
                            "type": "string",
                            "description": "The destination ID from the catalog, e.g. 'bad-gastein'",
                        },
                        "start_date": {
                            "type": "string",
                            "description": "Start date in YYYY-MM-DD format",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date in YYYY-MM-DD format",
                        },
                    },
                    "required": ["destination_id", "start_date", "end_date"],
                },
            }
        ]
    }


def fetch_weather(destination_id, start_date, end_date):
    """Call the Open-Meteo API for a destination's daily forecast.

    Why: Open-Meteo provides free weather forecasts (up to 16 days) without
    an API key, which is perfect for enriching travel recommendations.
    How: we look up the destination's coordinates, then request daily
    temperature, precipitation probability, and weather code data.
    """
    coords = DESTINATION_COORDS.get(destination_id)
    if not coords:
        log_gemini(f"No coordinates for destination '{destination_id}'. Skipping weather.")
        return {"error": f"Unknown destination: {destination_id}"}

    try:
        today = datetime.now().date()
        max_date = today + timedelta(days=15)

        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()

        # If the requested window is entirely in the past or entirely beyond 16 days
        if end < today or start > max_date:
            log_gemini(
                f"Requested dates {start_date} to {end_date} are entirely outside the "
                f"16-day forecast window [{today} , {max_date}]. Skipping Open-Meteo call."
            )
            return {
                "destination_id": destination_id,
                "dates": [],
                "temp_max": [],
                "temp_min": [],
                "precipitation_probability": [],
                "weather_code": [],
                "message": "Forecast is only available within 16 days from today.",
            }

        # Clamp to [today, max_date]
        clamped_start = max(start, today)
        clamped_end = min(end, max_date)

        if clamped_start > clamped_end:
            clamped_start = clamped_end

        query_start_date = clamped_start.strftime("%Y-%m-%d")
        query_end_date = clamped_end.strftime("%Y-%m-%d")
    except Exception as e:
        log_gemini(f"Error parsing dates {start_date} / {end_date}: {e}")
        return {"error": f"Invalid date format: {e}"}

    params = (
        f"latitude={coords['lat']}&longitude={coords['lon']}"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"
        f"&start_date={query_start_date}&end_date={query_end_date}"
        f"&timezone=auto"
    )
    url = f"{OPEN_METEO_URL}?{params}"
    log_gemini(f"Fetching weather from Open-Meteo for '{destination_id}'", {"url": url})

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as error:
        log_gemini(f"Open-Meteo request failed for '{destination_id}'", {"error": str(error)})
        return {"error": str(error)}

    daily = data.get("daily", {})
    return {
        "destination_id": destination_id,
        "dates": daily.get("time", []),
        "temp_max": daily.get("temperature_2m_max", []),
        "temp_min": daily.get("temperature_2m_min", []),
        "precipitation_probability": daily.get("precipitation_probability_max", []),
        "weather_code": daily.get("weather_code", []),
    }


def execute_weather_tool_calls(response_payload):
    """Find functionCall parts in a Gemini response and execute them.

    Why: after Gemini decides which destinations need weather, we must
    actually fetch that data and give it back.
    How: we scan all candidate parts for functionCall entries, execute each
    one, and collect the results.
    """
    candidates = response_payload.get("candidates", [])
    if not candidates:
        return [], []

    parts = candidates[0].get("content", {}).get("parts", [])
    tool_calls = []
    weather_results = []

    for part in parts:
        fc = part.get("functionCall")
        if fc and fc.get("name") == "get_weather_forecast":
            args = fc.get("args", {})
            tool_calls.append(fc)
            result = fetch_weather(
                args.get("destination_id", ""),
                args.get("start_date", ""),
                args.get("end_date", ""),
            )
            weather_results.append({
                "function_call": fc,
                "result": result,
            })
            log_gemini(
                f"Weather tool call executed for '{args.get('destination_id')}'",
                {"dates": result.get("dates", [])[:3], "temp_max": result.get("temp_max", [])[:3]},
            )

    return tool_calls, weather_results


def extract_gemini_text(payload):
    """Pull the text answer out of Gemini's HTTP response.

    Why: Gemini wraps the final text inside nested response objects.
    How: we look at the first candidate and join its text parts together.
    """
    candidates = payload.get("candidates", [])
    if not candidates:
        return ""

    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(part.get("text", "") for part in parts)


def clean_json_text(text):
    """Clean common formatting wrappers around model JSON.

    Why: even with structured output enabled, an LLM can occasionally include
    markdown fences or return a JSON-looking object with tiny formatting issues.
    How: we remove code fences, keep the text between the first and last curly
    brace, and repair a common missing-comma pattern between pretty-printed
    JSON lines.
    """
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        cleaned = cleaned[first_brace:last_brace + 1]

    return re.sub(r'([}\]"\d])\s*\n\s*(")', r'\1,\n\2', cleaned)


def parse_gemini_json(response_text):
    """Parse Gemini JSON and log the raw text when parsing fails.

    Why: when Gemini returns malformed JSON, the normal error message only says
    where parsing failed, not what text caused it.
    How: we try direct parsing first, then parse a cleaned version, and if both
    fail we log a safe preview plus the full raw text only in verbose mode.
    """
    try:
        return json.loads(response_text)
    except json.JSONDecodeError as first_error:
        cleaned = clean_json_text(response_text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as second_error:
            log_gemini(
                "Gemini returned malformed JSON.",
                {
                    "first_error": str(first_error),
                    "second_error": str(second_error),
                    "raw_preview": response_text[:500],
                },
            )
            log_gemini(
                "Verbose raw Gemini text that failed JSON parsing:",
                {"raw_text": response_text},
                verbose_only=True,
            )
            raise second_error


def call_gemini(request_body, api_key):
    """Send a request to the Gemini API and return the raw response payload.

    Why: both the initial call and the tool-call follow-up share the same HTTP
    logic, so we factor it out.
    How: we POST the body to the Gemini endpoint, handle HTTP errors, and
    return the parsed JSON response.
    """
    log_gemini("Verbose Gemini request body:", request_body, verbose_only=True)

    request = urllib.request.Request(
        GEMINI_URL.format(model=GEMINI_MODEL),
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        log_gemini(f"Gemini HTTP error {error.code}", {"body": detail})
        raise RuntimeError(f"Gemini API error {error.code}: {detail}") from error


def parse_with_llm(query):
    """Ask Gemini to turn the user request into structured search data.

    Why: this is the smart path that can understand fuzzy requests like
    "something close to the beach on the Adriatic sea" and infer the right
    nearby concepts from the catalog.
    How: we send the prompt, destination catalog, and the raw query to Gemini
    with a weather tool declaration. If Gemini issues tool calls we execute
    them and send the results back for a final answer.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        log_gemini("GEMINI_API_KEY not found. Using local fallback search.")
        return None

    log_gemini(f"Calling Gemini model: {GEMINI_MODEL}")

    allowed_tags = sorted(TAG_SYNONYMS.keys())
    instructions = PROMPT_TEMPLATE.format(
        allowed_tags=json.dumps(allowed_tags, ensure_ascii=False),
        destination_catalog=build_destination_catalog(),
        current_year=CURRENT_YEAR,
    )

    user_content = {
        "role": "user",
        "parts": [{"text": f"{instructions}\n\nUser request:\n{query}"}],
    }

    request_body = {
        "contents": [user_content],
        "tools": [build_weather_tool()],
        "generationConfig": {
            "maxOutputTokens": 2400,
            "thinkingConfig": {
                "thinkingBudget": 0,
            },
        },
    }
    log_gemini(
        "Prepared request payload (pass 1, with weather tool).",
        {
            "model": GEMINI_MODEL,
            "user_query": query,
            "allowed_tags": allowed_tags,
            "destination_count": len(DESTINATIONS),
        },
    )

    # --- Pass 1: send query, Gemini may return tool calls or direct answer ---
    response_payload = call_gemini(request_body, api_key)

    log_gemini(
        "Gemini pass-1 response received.",
        {
            "candidate_count": len(response_payload.get("candidates", [])),
            "usage_metadata": response_payload.get("usageMetadata", {}),
        },
    )
    log_gemini("Verbose pass-1 response:", response_payload, verbose_only=True)

    # --- Check for tool calls ---
    tool_calls, weather_results = execute_weather_tool_calls(response_payload)
    collected_weather = {}

    if tool_calls:
        log_gemini(
            f"Gemini requested {len(tool_calls)} weather tool call(s). Sending results back.",
        )

        # Collect weather data for the frontend
        for wr in weather_results:
            dest_id = wr["result"].get("destination_id", "")
            if dest_id and "error" not in wr["result"]:
                collected_weather[dest_id] = wr["result"]

        # Build the model turn (what Gemini said)
        model_parts = response_payload["candidates"][0]["content"]["parts"]

        # Build function response parts
        function_response_parts = []
        for wr in weather_results:
            function_response_parts.append({
                "functionResponse": {
                    "name": "get_weather_forecast",
                    "response": wr["result"],
                }
            })

        # --- Pass 2: send weather data back, ask for final structured answer ---
        follow_up_body = {
            "contents": [
                user_content,
                {"role": "model", "parts": model_parts},
                {"role": "user", "parts": function_response_parts},
            ],
            "generationConfig": {
                "maxOutputTokens": 2400,
                "responseMimeType": "application/json",
                "responseSchema": build_llm_schema(),
                "thinkingConfig": {
                    "thinkingBudget": 0,
                },
            },
        }

        log_gemini("Sending pass-2 request with weather data for structured answer.")
        response_payload = call_gemini(follow_up_body, api_key)

        log_gemini(
            "Gemini pass-2 response received.",
            {
                "candidate_count": len(response_payload.get("candidates", [])),
                "usage_metadata": response_payload.get("usageMetadata", {}),
            },
        )
        log_gemini("Verbose pass-2 response:", response_payload, verbose_only=True)
    else:
        # No tool calls — re-send with structured schema for JSON output
        log_gemini("No tool calls. Re-sending with structured schema.")
        structured_body = {
            "contents": [user_content],
            "generationConfig": {
                "maxOutputTokens": 2400,
                "responseMimeType": "application/json",
                "responseSchema": build_llm_schema(),
                "thinkingConfig": {
                    "thinkingBudget": 0,
                },
            },
        }
        response_payload = call_gemini(structured_body, api_key)

        log_gemini(
            "Gemini structured response received.",
            {
                "candidate_count": len(response_payload.get("candidates", [])),
                "usage_metadata": response_payload.get("usageMetadata", {}),
            },
        )

    # --- Parse the final structured JSON ---
    response_text = extract_gemini_text(response_payload)
    if not response_text:
        raise RuntimeError("Gemini response did not contain JSON text.")

    parsed = parse_gemini_json(response_text)
    parsed["criteria"]["used_llm"] = True
    parsed["weather_forecasts"] = collected_weather
    log_gemini(
        "Parsed Gemini JSON.",
        {
            "criteria": parsed.get("criteria", {}),
            "recommendation_count": len(parsed.get("recommendations", [])),
            "weather_destinations": list(collected_weather.keys()),
        },
    )
    return parsed


def apply_points_calculation(destination, criteria):
    """Calculate the points needed and affordability for a destination."""
    points_per_night = destination.get("pointsPerNight", 10)
    duration = criteria.get("duration_days") or 7
    total_points = duration * points_per_night
    destination["totalPoints"] = total_points
    destination["duration_days"] = duration
    
    budget = criteria.get("budget")
    if budget is not None:
        destination["affordable"] = total_points <= budget
        destination["pointsShortfall"] = max(0, total_points - budget)
    
    return destination


def validate_llm_recommendations(llm_result, field_name):
    """Keep only LLM recommendations that point to destinations we really have.

    Why: the model may suggest ideas, but the UI should only show items that
    exist in our local destination list.
    How: we match by destination id, ignore duplicates, and copy over the
    score and short reasons from the model output.
    """
    by_id = {item["id"]: item for item in DESTINATIONS}
    known_countries = {item["country"] for item in DESTINATIONS}
    criteria = llm_result.get("criteria", {})
    requested_countries = set(criteria.get("countries", []))

    unknown_countries = requested_countries - known_countries
    if unknown_countries:
        log_gemini(
            "LLM requested countries outside the local catalog. Returning no results.",
            {"unknown_countries": sorted(unknown_countries)},
        )
        return []

    validated = []
    seen = set()

    for recommendation in llm_result.get(field_name, []):
        destination_id = recommendation.get("id")
        if destination_id not in by_id or destination_id in seen:
            continue

        destination = dict(by_id[destination_id])
        destination["score"] = int(recommendation.get("score", 0))
        destination["reasons"] = recommendation.get("reasons", [])[:4]
        
        apply_points_calculation(destination, criteria)
        
        validated.append(destination)
        seen.add(destination_id)

    return validated


def build_alternative_results(criteria, limit=3):
    """Find available destinations to suggest when direct matches are impossible.

    Why: if a requested region is unavailable, an empty result set is honest,
    but the user can still benefit from seeing what our catalog does have.
    How: we reuse the requested activity/style tags, ignore unavailable
    geography, and return a few local catalog options.
    """
    relaxed_criteria = dict(criteria)
    relaxed_criteria["countries"] = []
    alternatives = search_destinations(relaxed_criteria, require_all_tags=False)

    if not alternatives:
        alternatives = [dict(destination) for destination in DESTINATIONS[:limit]]
        for alternative in alternatives:
            alternative["score"] = 0
            alternative["reasons"] = ["available catalog option"]

    return alternatives[:limit]


def make_recommendation_text(criteria, results, alternative_results, unsupported_regions=None):
    """Create a short explanation for the search response.

    Why: the JSON should not only contain cards, it should also explain why the
    result set is empty or why alternatives are shown.
    How: we look at unsupported regions, direct matches, and alternatives and
    return one user-facing sentence.
    """
    if unsupported_regions:
        region_text = ", ".join(unsupported_regions)
        if alternative_results:
            names = ", ".join(item["name"] for item in alternative_results[:3])
            return f"No destinations are available in {region_text}. Available alternatives in our catalog: {names}."
        return f"No destinations are available in {region_text}."

    if results:
        return "These destinations best match the request."

    if alternative_results:
        names = ", ".join(item["name"] for item in alternative_results[:3])
        return f"No direct match was found. Available alternatives in our catalog: {names}."

    return "No matching destinations or alternatives are available in the current catalog."


def search_destinations(criteria, require_all_tags=True):
    """Rank destinations with simple local rules.

    Why: this is the fallback search engine, and also a safety net when the
    model is unavailable or gives weak results.
    How: we score destinations by matching tags, countries, and text, then
    sort the best matches first.
    """
    results = []
    requested_tags = criteria["tags"]
    requested_countries = criteria["countries"]

    for destination in DESTINATIONS:
        score = 0
        reasons = []
        destination_tags = set(destination["tags"])

        for tag in requested_tags:
            if tag in destination_tags:
                score += 10
                reasons.append(f"matches {tag}")

        if require_all_tags and requested_tags and len(reasons) < len(requested_tags):
            continue

        if requested_countries:
            if destination["country"] in requested_countries:
                score += 12
                reasons.append(f"in {destination['country']}")
            else:
                continue

        if not requested_tags and not requested_countries:
            haystack = normalize(
                " ".join([
                    destination["name"],
                    destination["location"],
                    destination["country"],
                    destination["description"],
                    " ".join(destination["tags"]),
                ])
            )
            words = [word for word in normalize(criteria["query"]).split() if len(word) > 3]
            score = sum(2 for word in words if word in haystack)
            if score:
                reasons.append("text match")

        if requested_tags and score == 0:
            continue

        if score > 0:
            result = dict(destination)
            result["score"] = score
            result["reasons"] = reasons[:4]
            apply_points_calculation(result, criteria)
            results.append(result)

    return sorted(results, key=lambda item: item["score"], reverse=True)


def fallback_recommendations(query):
    """Get a reliable answer without using the LLM.

    Why: the app should still work if Gemini is down or the key is missing.
    How: we parse the query locally, search the data, and if needed relax the
    match a bit so we can show the closest available options.
    """
    criteria = parse_trip_request(query)
    unsupported_regions = requested_unsupported_regions(query, criteria)
    if unsupported_regions:
        criteria["semantic_intent"] = unsupported_regions
        alternatives = build_alternative_results(criteria)
        return {
            "criteria": criteria,
            "results": [],
            "alternative_results": alternatives,
            "recommendation_text": make_recommendation_text(criteria, [], alternatives, unsupported_regions),
        }

    results = search_destinations(criteria, require_all_tags=True)

    if not results and criteria["tags"]:
        results = search_destinations(criteria, require_all_tags=False)
        for result in results:
            result["reasons"] = result.get("reasons", []) + ["closest available alternative"]

    return {
        "criteria": criteria,
        "results": results,
        "alternative_results": [],
        "recommendation_text": make_recommendation_text(criteria, results, []),
    }


def recommend_destinations(query):
    """Choose the best search path for one user request.

    Why: this is the top-level decision point for the API.
    How: we try Gemini first, validate the model's answers, and if anything
    fails we fall back to the local search logic.
    """
    try:
        llm_result = parse_with_llm(query)
    except Exception as error:
        log_gemini("Gemini call failed. Using local fallback search.", {"error": str(error)})
        fallback = fallback_recommendations(query)
        return fallback

    if llm_result:
        criteria = llm_result["criteria"]
        weather_forecasts = llm_result.get("weather_forecasts", {})
        unsupported_regions = requested_unsupported_regions(query, criteria)
        if unsupported_regions:
            criteria["semantic_intent"] = criteria.get("semantic_intent", []) + [
                f"No local destinations in {region}." for region in unsupported_regions
            ]
            alternatives = validate_llm_recommendations(llm_result, "alternative_recommendations")
            if not alternatives:
                alternatives = build_alternative_results(criteria)
            log_gemini(
                "User requested unsupported region. Returning no results.",
                {"unsupported_regions": unsupported_regions},
            )
            return {
                "criteria": criteria,
                "results": [],
                "alternative_results": alternatives,
                "recommendation_text": llm_result.get("recommendation_text")
                or make_recommendation_text(criteria, [], alternatives, unsupported_regions),
                "weather_forecasts": weather_forecasts,
            }

        results = validate_llm_recommendations(llm_result, "recommendations")
        alternatives = validate_llm_recommendations(llm_result, "alternative_recommendations")

        if not results:
            fallback = fallback_recommendations(query)
            alternatives = alternatives or fallback["results"]
            return {
                "criteria": criteria,
                "results": [],
                "alternative_results": alternatives,
                "recommendation_text": llm_result.get("recommendation_text")
                or make_recommendation_text(criteria, [], alternatives),
                "weather_forecasts": weather_forecasts,
            }

        return {
            "criteria": criteria,
            "results": results,
            "alternative_results": alternatives,
            "recommendation_text": llm_result.get("recommendation_text")
            or make_recommendation_text(criteria, results, alternatives),
            "weather_forecasts": weather_forecasts,
        }

    return fallback_recommendations(query)


class SearchHandler(BaseHTTPRequestHandler):
    """Small HTTP handler for the `/api/search` endpoint.

    Why: the frontend needs a simple HTTP endpoint it can call with a user
    request and get back JSON results.
    How: we handle OPTIONS for CORS and POST for search requests.
    """
    def do_OPTIONS(self):
        """Answer CORS preflight requests from the browser."""
        self.send_response(204)
        self.add_cors_headers()
        self.end_headers()

    def do_POST(self):
        """Read the user prompt, run search, and send JSON back."""
        if self.path != "/api/search":
            self.send_json({"error": "Not found"}, 404)
            return

        try:
            body_length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(body_length) or b"{}")
            query = str(payload.get("query", "")).strip()
            if not query:
                self.send_json({"error": "Missing query"}, 400)
                return

            self.send_json(recommend_destinations(query))
        except Exception as error:
            self.send_json({"error": str(error)}, 500)

    def send_json(self, payload, status=200):
        """Write a JSON response in the format browsers expect."""
        response = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.add_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def add_cors_headers(self):
        """Allow the local Vite app to call this API from the browser."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


def run():
    """Start the local HTTP server on port 8000.

    Why: this gives us a tiny API process for the frontend to talk to.
    How: we bind to localhost and keep serving requests until the process
    is stopped.
    """
    server = ThreadingHTTPServer(("localhost", 8000), SearchHandler)
    print("Search API running at http://localhost:8000/api/search")
    print(f"Using Gemini model: {GEMINI_MODEL}")
    server.serve_forever()


if __name__ == "__main__":
    run()
