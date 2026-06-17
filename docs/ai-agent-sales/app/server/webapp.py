from __future__ import annotations
import json
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.agent.graph import agent, normalize_session_id


app = FastAPI()


def cfg(session_id: str):
    return {"configurable": {"thread_id": session_id}}


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    session_id = normalize_session_id(body.get("session_id", "web:anon"))
    text = body.get("input")
    if not text:
        raise HTTPException(status_code=400, detail="Campo 'input' é obrigatório")
    try:
        result = await agent.ainvoke({"messages": [{"role": "user", "content": text}]}, config=cfg(session_id))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao invocar agente: {e}")
    structured = result.get("structured_response") or {}
    reply_text = structured.get("message") or ""
    return {
        "reply_text": reply_text,
        "intent": structured.get("intent", "general_chat"),
        "structured": structured,
        "trace_id": result.get("run_id", ""),
    }


@app.get("/stream")
async def stream(session_id: str, input: str):
    sid = normalize_session_id(session_id)

    async def gen():
        async for chunk in agent.astream({"messages": [{"role": "user", "content": input}]}, config=cfg(sid)):
            yield f"data: {chunk}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")

