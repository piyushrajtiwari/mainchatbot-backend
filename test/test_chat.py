import asyncio
import json
import unittest
from contextlib import asynccontextmanager
from os import environ
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

import requests
from duckduckgo_search.exceptions import RatelimitException
from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

# Use local placeholder settings so the tests can run without a configured .env.
with patch.dict(environ, {
    "SECRET_KEY": "test-signing-key",
    "ALGORITHM": "HS256",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "15",
    "REFRESH_TOKEN_EXPIRE_DAYS": "7",
    "GROQ_API_KEY": "test-groq-key",
    "AVIATIONSTACK_KEY": "test-aviation-key",
    "DATABASE_URL": "postgresql+asyncpg://test:test@127.0.0.1:5432/test",
    "DIRECT_URL": "postgresql+asyncpg://test:test@127.0.0.1:5432/test",
    "CHECKPOINT_DATABASE_URL": "postgresql://test:test@127.0.0.1:5432/test",
    "RESEND_API_KEY": "test-resend-key",
    "FROM_EMAIL": "test@example.com",
    "BACKEND_URL": "http://127.0.0.1:8000",
    "FRONTEND_URL": "http://localhost:5173",
    "CORS_ORIGINS": '["http://localhost:5173"]',
}):
    from app.chat import router, service, tools
    from app.chat.schema import ChatMessage
    from app.main import app, lifespan


class ChatTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_list_queries_checkpoints_for_current_user(self):
        user = SimpleNamespace(id=UUID(int=1))
        conn = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
            fetchall=lambda: [(f"{user.id}:recent", "checkpoint-2"),
                             (f"{user.id}:older", "checkpoint-1")]
        )))

        @asynccontextmanager
        async def connect():
            yield conn

        workflow = SimpleNamespace(aget_state=AsyncMock(side_effect=[
            SimpleNamespace(metadata={"title": "Recent chat"}, values={}),
            SimpleNamespace(metadata={}, values={"messages": [
                SimpleNamespace(type="human", content="Older message")]}),
        ]))
        with patch.object(router, "checkpoint_engine", SimpleNamespace(connect=connect)), \
                patch.object(router, "get_workflow", return_value=workflow):
            chats = await router.get_chats(user)

        self.assertEqual(chats, [
            {"id": "recent", "title": "Recent chat", "user_id": str(user.id)},
            {"id": "older", "title": "Older message", "user_id": str(user.id)},
        ])
        self.assertEqual(conn.execute.await_args.args[1], {"prefix": f"{user.id}:%"})
        self.assertEqual(
            [call.args[0]["configurable"]["thread_id"]
             for call in workflow.aget_state.await_args_list],
            [f"{user.id}:recent", f"{user.id}:older"],
        )

    async def test_checkpoint_keys_isolate_users_and_preserve_continuity(self):
        histories = {}

        class Workflow:
            async def astream(self, state, *, config, stream_mode, version):
                key = config["configurable"]["thread_id"]
                history = histories.setdefault(key, [])
                history.append(state["messages"][0].content)
                yield {"type": "updates", "data": {
                    "chat_node": {"messages": [AIMessage(content="|".join(history))]}}}

        async def send(user_id, thread_id, message):
            response = await router.chat(
                ChatMessage(messages=message, thread_id=thread_id),
                SimpleNamespace(id=UUID(int=user_id)),
            )
            return [json.loads(chunk) async for chunk in response.body_iterator]

        with patch.object(router, "get_workflow", return_value=Workflow()):
            await send(1, "shared", "private")
            other = await send(2, "shared", "hello")
            same = await send(1, "shared", "again")
            separate = await send(1, "other", "new")
            crafted = await send(2, f"{UUID(int=1)}:shared", "attempt")
        self.assertEqual(other[0]["content"], "hello")
        self.assertEqual(same[0]["content"], "private|again")
        self.assertEqual(separate[0]["content"], "new")
        self.assertEqual(crafted[0]["content"], "attempt")
        self.assertEqual(same[-1], {"type": "done"})

    async def test_graph_executes_bound_tool_and_exposes_only_final_text(self):
        bound_names = {tool["function"]["name"] for tool in service.llm.kwargs["tools"]}
        self.assertEqual(bound_names, {"get_weather", "search_web", "get_flight_delay_prediction"})
        workflow = service.graph.compile(checkpointer=InMemorySaver())
        model = AsyncMock(side_effect=[
            AIMessage(content="Internal planning text", tool_calls=[{
                "name": "get_weather", "args": {"city": "Delhi"}, "id": "weather-call",
            }]),
            AIMessage(content=[
                {"type": "reasoning", "reasoning": "Hidden reasoning"},
                {"type": "text", "text": "Delhi is clear."},
            ]),
        ])
        user = SimpleNamespace(id=UUID(int=1))
        message = ChatMessage(messages="Weather in Delhi?", thread_id="weather")
        with patch.object(service, "llm", SimpleNamespace(ainvoke=model)), \
                patch.object(router, "get_workflow", return_value=workflow), \
                patch.object(tools.requests, "get", side_effect=[
                    geocoding_response(), provider_response({"current": {"temperature_2m": 23, "weather_code": 0}}),
                ]) as request:
            response = await router.chat(message, user)
            records = [json.loads(chunk) async for chunk in response.body_iterator]
            history = await router.get_current_chat("weather", user)

        self.assertEqual(request.call_count, 2)
        self.assertEqual(model.await_count, 2)
        tool_result = model.await_args.args[0][-1]
        self.assertIsInstance(tool_result, ToolMessage)
        self.assertIn("Temperature: 23", tool_result.content)
        self.assertEqual(records, [
            {"type": "token", "content": "Delhi is clear."}, {"type": "done"},
        ])
        self.assertEqual(history, [
            {"type": "human", "content": "Weather in Delhi?"}, {"type": "ai", "content": "Delhi is clear."},
        ])

    async def test_graph_can_answer_without_running_a_tool(self):
        workflow = service.graph.compile()
        model = AsyncMock(return_value=AIMessage(content="Hello!"))
        user = SimpleNamespace(id=UUID(int=1))
        with patch.object(service, "llm", SimpleNamespace(ainvoke=model)), \
                patch.object(router, "get_workflow", return_value=workflow), \
                patch.object(tools.requests, "get") as request, patch.object(tools, "DDGS") as search:
            response = await router.chat(ChatMessage(messages="Hi", thread_id="hello"), user)
            records = [json.loads(chunk) async for chunk in response.body_iterator]

        model.assert_awaited_once()
        request.assert_not_called()
        search.assert_not_called()
        self.assertEqual(records, [{"type": "token", "content": "Hello!"}, {"type": "done"}])

    async def test_empty_ai_text_and_tool_updates_do_not_emit_tokens(self):
        async def updates(*args, **kwargs):
            yield {"type": "updates", "data": {"tools": {"messages": [
                ToolMessage(content="Internal tool content", tool_call_id="lookup"),
            ]}}}
            yield {"type": "updates", "data": {"chat_node": {"messages": [
                AIMessage(content=" "), AIMessage(content=[{"type": "reasoning", "reasoning": "Private"}]),
            ]}}}

        user = SimpleNamespace(id=UUID(int=1))
        with patch.object(router, "get_workflow", return_value=SimpleNamespace(astream=updates)):
            response = await router.chat(ChatMessage(messages="Look up this", thread_id="empty"), user)
            records = [json.loads(chunk) async for chunk in response.body_iterator]
        self.assertEqual(records, [{"type": "done"}])

    async def test_cancelling_the_response_closes_the_graph_stream(self):
        started = asyncio.Event()
        closed = asyncio.Event()

        async def updates(*args, **kwargs):
            try:
                started.set()
                await asyncio.Future()
                yield {"type": "updates", "data": {}}
            finally:
                closed.set()

        user = SimpleNamespace(id=UUID(int=1))
        with patch.object(router, "get_workflow", return_value=SimpleNamespace(astream=updates)):
            response = await router.chat(ChatMessage(messages="Look up this", thread_id="cancel"), user)
            pending = asyncio.create_task(anext(response.body_iterator))
            try:
                await asyncio.wait_for(started.wait(), timeout=2)
            finally:
                pending.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await pending
        self.assertTrue(closed.is_set())

    async def test_stream_errors_do_not_expose_provider_details(self):
        async def updates(*args, **kwargs):
            yield {"type": "updates", "data": {}}
            raise RuntimeError("private provider detail")

        user = SimpleNamespace(id=UUID(int=1))
        with patch.object(router, "get_workflow", return_value=SimpleNamespace(astream=updates)), \
                self.assertLogs(router.logger, level="ERROR") as logs:
            response = await router.chat(ChatMessage(messages="Hi", thread_id="error"), user)
            records = [json.loads(chunk) async for chunk in response.body_iterator]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["type"], "error")
        self.assertIn("could not finish", records[0]["content"])
        self.assertNotIn("private provider detail", records[0]["content"])
        self.assertNotIn("private provider detail", "\n".join(logs.output))

    async def test_checkpoint_stays_open_until_app_shutdown(self):
        events = []
        saver = SimpleNamespace(setup=AsyncMock())
        compiled = object()

        @asynccontextmanager
        async def connection(_url):
            events.append("open")
            try:
                yield saver
            finally:
                events.append("close")

        with patch.object(service.AsyncPostgresSaver, "from_conn_string", connection), \
                patch.object(service.graph, "compile", return_value=compiled):
            async with lifespan(app):
                self.assertEqual(events, ["open"])
                self.assertIs(service.get_workflow(), compiled)
                saver.setup.assert_awaited_once()
            self.assertEqual(events, ["open", "close"])
            with self.assertRaises(HTTPException) as caught:
                service.get_workflow()
            self.assertEqual(caught.exception.status_code, 503)

    async def test_failed_startup_closes_checkpoint_connection(self):
        events = []

        @asynccontextmanager
        async def connection(_url):
            try:
                yield SimpleNamespace(setup=AsyncMock(side_effect=RuntimeError("setup failed")))
            finally:
                events.append("close")

        with patch.object(service.AsyncPostgresSaver, "from_conn_string", connection):
            with self.assertRaisesRegex(RuntimeError, "setup failed"):
                async with lifespan(app):
                    self.fail("Startup must fail")
        self.assertEqual(events, ["close"])
        self.assertIsNone(service.workflow)


def provider_response(payload=None, *, status=200, body=None):
    response = requests.Response()
    response.url = "https://provider.example/test"
    response.status_code = status
    response._content = json.dumps(payload).encode() if body is None else body
    return response


def geocoding_response():
    return provider_response({"results": [
        {"latitude": 28.6, "longitude": 77.2, "name": "Delhi", "country": "India"},
    ]})


class ToolTests(unittest.TestCase):
    def test_weather_geocoding_failures_are_distinct_from_no_results(self):
        for response in (
            provider_response({"results": []}, status=401),
            provider_response({"error": True, "reason": "private detail"}),
            provider_response(body=b"invalid JSON"),
            provider_response({"results": [{}]}),
            provider_response({"results": {"name": "Delhi"}}),
        ):
            with self.subTest(body=response.content), patch.object(tools.requests, "get", return_value=response):
                result = tools.get_weather.invoke({"city": "Delhi"})
                self.assertEqual(result, "Current weather is unavailable. Please try again.")

        for payload in ({"results": []}, {"generationtime_ms": 0.1}):
            with self.subTest(payload=payload), patch.object(tools.requests, "get", return_value=provider_response(payload)):
                self.assertIn("not found", tools.get_weather.invoke({"city": "No match"}))

    def test_weather_forecast_failures_return_a_clean_error(self):
        for response in (
            provider_response({"current": {"weather_code": 0}}, status=429),
            provider_response({}, status=500),
            provider_response(body=b"not JSON"),
            provider_response({"current": []}),
            provider_response({"current": {"temperature_2m": "cold"}}),
            provider_response({"current": {"weather_code": [66]}}),
        ):
            with self.subTest(body=response.content), patch.object(tools.requests, "get", side_effect=[
                geocoding_response(), response,
            ]):
                self.assertEqual(
                    tools.get_weather.invoke({"city": "Delhi"}),
                    "Current weather is unavailable. Please try again.",
                )

    def test_weather_describes_supported_codes_and_has_an_unknown_fallback(self):
        for code, condition in {
            48: "Rime fog", 57: "Dense freezing drizzle", 66: "Light freezing rain",
            75: "Heavy snowfall", 77: "Snow grains", 86: "Heavy snow showers",
            96: "Thunderstorm with light hail", 700: "Unknown",
        }.items():
            with self.subTest(code=code), patch.object(tools.requests, "get", side_effect=[
                geocoding_response(), provider_response({"current": {"weather_code": code, "temperature_2m": 0}}),
            ]):
                result = tools.get_weather.invoke({"city": "Delhi"})
                self.assertIn(f"Condition: {condition}\n", result)
                self.assertIn("Temperature: 0°C", result)

    def test_flight_https_and_departure_delay_semantics(self):
        for fields, expected in (
            ({}, "Departure delay: Unknown"),
            ({"delay": None}, "Departure delay: Unknown"),
            ({"delay": 0}, "0 minutes reported (on time)"),
            ({"delay": 22}, "Departure delay: 22 minutes reported"),
            ({"delay": False}, "Flight status is unavailable"),
        ):
            payload = {"data": [{"flight_status": "scheduled", "departure": fields}]}
            with self.subTest(fields=fields), patch.object(
                tools.requests, "get", return_value=provider_response(payload),
            ) as request:
                self.assertIn(expected, tools.get_flight_delay_prediction.invoke({"flight_iata": "6e 2017"}))
                request.assert_called_once_with(
                    "https://api.aviationstack.com/v1/flights",
                    params={"access_key": "test-aviation-key", "flight_iata": "6E2017"},
                    timeout=15, allow_redirects=False,
                )

    def test_flight_provider_failures_do_not_echo_details_or_report_missing_flights(self):
        for response in (
            provider_response({"data": []}, status=302),
            provider_response({"data": []}, status=401),
            provider_response({"data": []}, status=429),
            provider_response({"data": []}, status=500),
            provider_response({"error": {"message": "private detail"}}),
            provider_response(body=b"invalid JSON"),
            provider_response({"data": {}}),
            provider_response({"data": [None]}),
            provider_response({"data": [{"flight_status": "active", "departure": []}]}),
        ):
            with self.subTest(status=response.status_code, body=response.content), patch.object(
                tools.requests, "get", return_value=response,
            ):
                result = tools.get_flight_delay_prediction.invoke({"flight_iata": "6E2017"})
                self.assertEqual(result, "Flight status is unavailable. Please try again.")

        with patch.object(tools.requests, "get", side_effect=requests.Timeout("private key in request URL")):
            self.assertEqual(
                tools.get_flight_delay_prediction.invoke({"flight_iata": "6E2017"}),
                "Flight status is unavailable. Please try again.",
            )
        with patch.object(tools.requests, "get", return_value=provider_response({"data": []})):
            self.assertIn("not found", tools.get_flight_delay_prediction.invoke({"flight_iata": "6E2017"}))

    def test_airport_weather_is_optional_and_does_not_assert_a_delay_cause(self):
        flight = {"data": [{"flight_status": "active", "departure": {"iata": "DEL", "delay": 22}}]}
        for weather, expected in (
            (provider_response([{"rawOb": "VIDP 010730Z 00000KT 0200 FG"}]), "VIDP 010730Z"),
            (provider_response([], status=500), None),
            (provider_response([None]), None),
        ):
            with self.subTest(body=weather.content), patch.object(tools.requests, "get", side_effect=[
                provider_response(flight), weather,
            ]):
                result = tools.get_flight_delay_prediction.invoke({"flight_iata": "6E2017"})
                self.assertIn("Departure delay: 22 minutes reported", result)
                self.assertIn("Delay reason: Unconfirmed", result)
                if expected:
                    self.assertIn(expected, result)
                else:
                    self.assertNotIn("(METAR)", result)

    def test_search_provider_errors_are_sanitized(self):
        with patch.object(tools, "DDGS") as ddgs:
            search = ddgs.return_value.__enter__.return_value.text
            search.side_effect = RatelimitException("private provider details")
            self.assertEqual(
                tools.search_web.invoke({"query": "test query"}),
                "Web search is unavailable. Please try again.",
            )
            search.assert_called_once_with("test query", max_results=5)


if __name__ == "__main__":
    unittest.main()
