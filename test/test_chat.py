import json
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi import HTTPException
from app.core.settings import settings

# Import without requiring a real provider key; no external services are called.
with patch.object(settings, "GROQ_API_KEY", "test-placeholder"):
    from app.chat import service, router
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
            async def astream_events(self, state, config, version):
                key = config["configurable"]["thread_id"]
                history = histories.setdefault(key, [])
                history.append(state["messages"][0].content)
                yield {"event": "on_chat_model_stream", "data": {
                    "chunk": SimpleNamespace(content="|".join(history))}}

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


if __name__ == "__main__":
    unittest.main()
