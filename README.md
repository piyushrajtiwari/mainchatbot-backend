# MainChatbot backend

FastAPI service for the MainChatbot web app. It handles account registration, email verification, password recovery, and authenticated chat. LangGraph sends messages to Groq, streams replies to the browser, and stores conversation state in PostgreSQL. The assistant can also look up current weather, search the web, and retrieve flight status. [Chat tools and provider behavior](doc/PROJECT_GUIDE.md#chat-tools)

## Run locally

Run the commands from `backend_chatbot/`. You need Python 3.10 or newer, PostgreSQL, a Groq API key with access to the configured model, a Resend API key with an authorized sender address, and an AviationStack API key for flight status.

1. Create a virtual environment and install the pinned dependencies.

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```

   On macOS or Linux, activate with `source .venv/bin/activate`. If PowerShell blocks activation, use `.\.venv\Scripts\python.exe` in place of `python` for the remaining commands.

2. Create `.env` in this directory and replace the placeholders. The three database URLs can point to the same local PostgreSQL database.

   ```dotenv
   SECRET_KEY=replace-with-a-random-signing-secret
   ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_MINUTES=15
   REFRESH_TOKEN_EXPIRE_DAYS=7

   DATABASE_URL=postgresql+asyncpg://mainchatbot:local-password@127.0.0.1:5432/mainchatbot
   DIRECT_URL=postgresql+asyncpg://mainchatbot:local-password@127.0.0.1:5432/mainchatbot
   CHECKPOINT_DATABASE_URL=postgresql://mainchatbot:local-password@127.0.0.1:5432/mainchatbot

   GROQ_API_KEY=replace-with-groq-key
   AVIATIONSTACK_KEY=replace-with-aviationstack-key
   RESEND_API_KEY=replace-with-resend-key
   FROM_EMAIL="MainChatbot <hello@example.com>"
   BACKEND_URL=http://127.0.0.1:8000
   FRONTEND_URL=http://localhost:5173
   CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
   ```

   You can generate a signing secret with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Set `FRONTEND_URL` to the browser origin you actually use so verification and reset emails open the React app. The backend requires `AVIATIONSTACK_KEY` at startup. For unit tests, set a placeholder value.

3. Apply the auth migrations and start the server.

   ```sh
   python -m alembic upgrade head
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```

   The app initializes the LangGraph checkpoint tables on startup. Open [the health endpoint](http://127.0.0.1:8000/health) or [the interactive API reference](http://127.0.0.1:8000/docs). For the browser app, follow the README in the sibling `frontend_chatbot/` directory.

## Tests

Run the unit tests with the backend settings present. It is safe to use placeholder credentials and syntactically valid PostgreSQL URLs for this suite. The chat tests mock the database and model workflow, and the middleware tests use an in-process FastAPI app.

```sh
python -m unittest discover -s test -v
```

The current suite has one known failure. The chat continuity test mocks `astream_events`, while the router now calls `astream`. The other eight tests pass.

## Documentation

| Document | Contents |
| --- | --- |
| [Project guide](doc/PROJECT_GUIDE.md) | Architecture, chat tools, database setup, API contracts, and troubleshooting |
| [HTTP middleware](MIDDLEWARE.md) | Request IDs, security headers, streaming, and CORS |
| [Changelog](CHANGELOG.md) | Current unreleased changes |
