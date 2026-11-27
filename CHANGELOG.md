# MainChatbot backend changelog

## Unreleased

### Added

- FastAPI health endpoint and generated OpenAPI documentation.
- Registration, email verification, sign-in, rotating refresh sessions, and sign-out.
- Password recovery with 15-minute, single-use reset tokens, plus authenticated password changes.
- PostgreSQL-backed chat persistence, incremental Groq replies, and an account-scoped conversation list.
- `GET /chat/current-chat/{thread_id}` for retrieving the selected thread's saved human and assistant messages.
- Model-driven chat tools for current weather, web search, and flight status, with airport weather context for supported Indian airports.
- Request IDs, response timing, security headers, and explicit credentialed CORS through the shared middleware.
- Backend setup instructions, an API and architecture guide, and Git ignore rules for local environment files, virtual environments, and generated Python files.

### Changed

- The LangGraph workflow can execute a requested tool and pass its result back to Groq before continuing the response.
- Startup configuration now requires `AVIATIONSTACK_KEY` for the flight-status integration.
- Verification and reset emails target the React app when `FRONTEND_URL` is configured. Existing backend reset links redirect to the React reset page with their original token.
