import unittest

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.core.middleware import configure_middleware


class MiddlewareTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        configure_middleware(app, origins=["http://localhost:5173"])

        @app.get("/auth/me")
        async def me(request: Request):
            return {"request_id": request.state.request_id}

        @app.get("/fail")
        async def fail():
            raise RuntimeError("secret-database-credential")

        @app.get("/unauthorized")
        async def unauthorized():
            raise HTTPException(401, "Please sign in")

        @app.get("/stream")
        async def stream():
            async def chunks():
                yield "first"
                yield "second"
            return StreamingResponse(chunks())

        self.client = TestClient(app)

    def test_headers_and_request_identity(self):
        response = self.client.get("/auth/me")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.json()["request_id"], response.headers["X-Request-ID"])
        self.assertGreaterEqual(float(response.headers["X-Process-Time"]), 0)
        self.assertNotEqual(response.headers["X-Request-ID"], self.client.get("/auth/me").headers["X-Request-ID"])

    def test_credentialed_cors_and_preflight(self):
        response = self.client.options("/auth/me", headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], "http://localhost:5173")
        self.assertEqual(response.headers["Access-Control-Allow-Credentials"], "true")
        denied = self.client.get("/auth/me", headers={"Origin": "https://untrusted.example"})
        self.assertNotIn("Access-Control-Allow-Origin", denied.headers)

    def test_error_response_is_generic_and_has_cors(self):
        response = self.client.get("/fail", headers={"Origin": "http://localhost:5173"})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "Internal server error")
        self.assertNotIn("secret", response.text)
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], "http://localhost:5173")
        self.assertIn("X-Request-ID", response.headers)

    def test_auth_errors_docs_and_streams_are_preserved(self):
        response = self.client.get("/unauthorized")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Please sign in")
        self.assertNotIn("Content-Security-Policy", self.client.get("/docs").headers)
        self.assertEqual(self.client.get("/stream").text, "firstsecond")

    def test_wildcard_origins_are_rejected(self):
        with self.assertRaises(ValueError):
            configure_middleware(FastAPI(), origins=["*"])


if __name__ == "__main__":
    unittest.main()
