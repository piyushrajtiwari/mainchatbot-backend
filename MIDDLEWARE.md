# Core HTTP middleware

`app/core/middleware.py` registers `CoreMiddleware` and credentialed CORS through
`configure_middleware` in `app/main.py`. Authentication stays in `CurrentUser`.

The middleware adds security headers, an independent request ID available through
`request.state.request_id`, and `X-Process-Time` in seconds until response headers.
Auth responses use `Cache-Control: no-store`. API docs retain their CDN scripts.
Unexpected errors before response start return generic JSON with a request ID;
errors after streaming starts propagate without writing a second response.
Logs omit request bodies, query strings, cookies, and credentials.

Configure `CORS_ORIGINS` as a JSON array of exact origins in the backend `.env`:

```dotenv
CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
FRONTEND_URL=http://localhost:5173
```

The origin of `FRONTEND_URL` is also allowed. Wildcards are rejected because auth
uses cookies. Set explicit production origins when deploying. CORS is a browser
policy, not authentication or a substitute for CSRF protection. Keep frontend and
API same-origin for the existing SameSite=Lax cookie behavior.

Run `python -m unittest discover -s test -p test_middleware.py` from this directory.
