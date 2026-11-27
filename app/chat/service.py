from contextlib import asynccontextmanager
from fastapi import HTTPException
from typing import Annotated, TypedDict
from app.core.settings import settings
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END, add_messages
from langchain_core.messages import BaseMessage,SystemMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from app.core.prompts import system_prompt


llm = ChatGroq(
    model="openai/gpt-oss-120b",
    temperature=0.5,
    api_key=settings.GROQ_API_KEY,
    streaming=True,
)

class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

async def chat_node(state: ChatState):
    message_all = [SystemMessage(content=system_prompt)]+state["messages"]
    result = await llm.ainvoke(message_all)
    return {"messages": [result]}

graph = StateGraph(ChatState)


graph.add_node("chat_node", chat_node)

graph.add_edge(START, "chat_node")
graph.add_edge("chat_node", END)


workflow = None

@asynccontextmanager
async def init_workflow():
    global workflow
    async with AsyncPostgresSaver.from_conn_string(
        settings.CHECKPOINT_DATABASE_URL
    ) as saver:
        try:
            await saver.setup()
            workflow = graph.compile(checkpointer=saver)
            yield workflow
        finally:
            workflow = None

def get_workflow():
    if workflow is None:
        raise HTTPException(status_code=503, detail="Chat service is not ready")
    return workflow

