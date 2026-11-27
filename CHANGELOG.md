# MainChatbot backend changelog

## Unreleased

### Added

- FastAPI health endpoint and generated OpenAPI documentation.
- Registration, email verification, sign-in, rotating refresh sessions, and sign-out.
- Password recovery with 15-minute, single-use reset tokens, plus authenticated password changes.
- PostgreSQL-backed chat persistence, Groq replies over NDJSON, and an account-scoped conversation list.
- `GET /chat/current-chat/{thread_id}` for retrieving the selected thread's saved human and assistant messages.
- Model-driven chat tools for current weather, web search, and flight status, with airport weather context for supported Indian airports.
- Request IDs, response timing, security headers, and explicit credentialed CORS through the shared middleware.
- Backend setup instructions, an API and architecture guide, and Git ignore rules for local environment files, virtual environments, and generated Python files.

### Changed

- The LangGraph workflow can execute a requested tool and pass its result back to Groq before continuing the response.
- Startup configuration now requires `AVIATIONSTACK_KEY` for the flight-status integration.
- Verification and reset emails target the React app when `FRONTEND_URL` is configured. Existing backend reset links redirect to the React reset page with their original token.
- Chat responses emit completed assistant text after any tool calls finish. Internal tool messages and tool-calling turns are excluded from the stream and saved transcript API.

### Fixed

- AviationStack requests use HTTPS and refuse redirects. The flight tool distinguishes missing delay data from an explicit zero and reports weather as context for an unconfirmed cause.
- Provider HTTP errors, malformed responses, and timeouts return generic messages. The weather tool recognizes additional freezing precipitation, snow, and thunderstorm codes.
- Mocked tests cover tool routing, direct replies, cancellation, transcript filtering, and upstream failures. The chat continuity test now matches the graph's stream format.
