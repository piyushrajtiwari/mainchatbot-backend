import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage,AIMessage,ToolMessage
from app.chat.schema import ChatMessage
from app.auth.dependancy import CurrentUser
from app.chat.service import get_workflow
from app.chat.config import make_config
from app.db.config import checkpoint_engine
from sqlalchemy import text


router = APIRouter(prefix="/chat", tags=["chat"])



@router.post("/chat-message")
async def chat(data: ChatMessage, user: CurrentUser):
    workflow = get_workflow()

    async def event():
        config = make_config(data,user)

        try:
            async for chunk in workflow.astream(
                {"messages": [HumanMessage(content=data.messages)]},
                config=config,
                stream_mode="messages",
                version="v2",
            ):
                # v2 -> dict {"type", "data"}; purane versions -> (msg, metadata) tuple
                if isinstance(chunk, dict):
                    if chunk.get("type") != "messages":
                        continue
                    msg, metadata = chunk["data"]
                else:
                    msg, metadata = chunk
                    
                if isinstance(msg, ToolMessage):
                    continue

                if isinstance(msg, AIMessage):
                    if msg.tool_calls:
                        continue

                    if msg.content:
                        if isinstance(msg.content, str):
                            yield json.dumps({"type": "token", "content": msg.content}) + "\n"
            yield json.dumps({"type": "done"}) + "\n"
        except Exception as e:
            print("Chat error:", repr(e), flush=True)
            yield json.dumps({"type": "error", "content": str(e)}) + "\n"

    return StreamingResponse(
        event(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/chats")
async def get_chats(user: CurrentUser):
    workflow = get_workflow()

    # 1. Sabse pehle checkpoints table se thread_id lao, recent pehle wale order me
    async with checkpoint_engine.connect() as conn:
        result = await conn.execute(
            text("""
                SELECT thread_id, MAX(checkpoint_id) as last_time
                FROM checkpoints
                WHERE thread_id LIKE :prefix
                GROUP BY thread_id
                ORDER BY last_time DESC
            """),
            {"prefix": f"{user.id}:%"}
        )
        rows = result.fetchall()
        # rows = [('111-aaa:chat-3', ...), ('111-aaa:chat-2', ...), ...]
        # Ab ye recent first order me hai, chat-3 sabse upar

    chats = []
    for r in rows:
        full_id = r[0]  # '111-aaa:chat-3'
        chat_id = full_id.split(":", 1)[1]  # 'chat-3'

        # 2. Har chat ka title metadata se nikalo
        temp_data = ChatMessage(messages="", thread_id=chat_id, title=None)
        config = make_config(temp_data, user)
        state = await workflow.aget_state(config)

        title = "New Chat"
        if state and state.metadata:
            title = state.metadata.get("title", "New Chat")

        # Agar metadata me title nahi hai (purane chats ke liye), to pehle message se le lo
        if title == "New Chat" and state and state.values.get("messages"):
            for m in state.values["messages"]:
                if m.type == "human":
                    title = m.content[:60]
                    break

        chats.append({
            "id": chat_id,      # frontend ko ye chahiye
            "title": title,     # sidebar me ye dikhega
            "user_id": str(user.id)  # tu ye bhi maang raha tha, ye bhi de diya
        })

    return chats 

@router.get("/current-chat/{thread_id}")
async def get_current_chat(thread_id:str,user:CurrentUser):
    current_chat = []
    
    workflow = get_workflow()
    temp_data = ChatMessage(messages="", thread_id=thread_id, title=None)
    config = make_config(temp_data, user)
    state = await workflow.aget_state(config)
    
    messages = state.values.get("messages", []) if state.values else []
    
    for cur in messages :  
        if isinstance(cur,HumanMessage):
            current_chat.append({"type":"human","content":cur.content}) 
        elif isinstance(cur,AIMessage):
            if cur.content:
                current_chat.append({"type":"ai","content":cur.content}) 
        else:
            continue
        
    return current_chat 
    
