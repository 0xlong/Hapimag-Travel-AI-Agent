# Natural Language Search Backend

Run the API:

```powershell
npm run api
```

The backend automatically loads `GEMINI_API_KEY` from the project-root `.env` file.

Example `.env`:

```text
GEMINI_API_KEY=your_google_ai_studio_key
```

Optional model override:

```powershell
GEMINI_MODEL=gemini-2.5-flash
```

Gemini logs:

Safe Gemini logs are enabled by default and are written to the terminal plus:

```text
backend/gemini_debug.log
```

To turn logs off:

```text
DEBUG_GEMINI=false
```

This prints safe Gemini logs such as model name, request summary, token usage metadata, parsed criteria, and recommendation count. It does not print your API key.

Optional verbose Gemini logs:

```text
DEBUG_GEMINI_VERBOSE=true
```

Verbose mode prints the larger request and response payloads. Use it only while debugging because it can include the full prompt, destination catalog, and user query.

The LLM prompt lives in:

```text
backend/prompts/trip_search_prompt.txt
```

The backend asks Gemini to return structured JSON with search criteria and ranked destination IDs. Returned IDs are validated against `destinations.json`, so the UI only displays local destinations.

If `GEMINI_API_KEY` is missing or the LLM request fails, the server falls back to the local keyword matcher.
