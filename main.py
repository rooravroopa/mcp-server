import hashlib

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

EMAIL = "22f3000579@ds.study.iitm.ac.in"  # trimmed + lowercase

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

SUPPORTED_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]

TOOL = {
    "name": "solve_challenge",
    "description": "Reads the exam challenge from the HTTP headers and returns the answer.",
    "inputSchema": {"type": "object", "properties": {}},
}


def compute_answer(challenge: str) -> str:
    """first 16 hex chars of SHA-256("<challenge>:<email>")"""
    return hashlib.sha256(f"{challenge}:{EMAIL}".encode()).hexdigest()[:16]


def handle_message(msg: dict, headers) -> dict | None:
    """Handle ONE JSON-RPC message. Returns a reply dict, or None for notifications."""
    method = msg.get("method")
    msg_id = msg.get("id")

    # Notifications (no id) get no reply, e.g. notifications/initialized
    if msg_id is None:
        return None

    def ok(result):
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def err(code, text):
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": text}}

    if method == "initialize":
        asked = (msg.get("params") or {}).get("protocolVersion")
        version = asked if asked in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0]
        return ok({
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "challenge-server", "version": "1.0.0"},
        })

    if method == "ping":
        return ok({})

    if method == "tools/list":
        return ok({"tools": [TOOL]})

    if method == "tools/call":
        name = (msg.get("params") or {}).get("name")
        if name != "solve_challenge":
            return err(-32602, f"Unknown tool: {name}")
        challenge = headers.get("x-exam-challenge")  # header names are case-insensitive
        if not challenge:
            return ok({
                "content": [{"type": "text", "text": "Missing X-Exam-Challenge header"}],
                "isError": True,
            })
        return ok({"content": [{"type": "text", "text": compute_answer(challenge)}]})

    return err(-32601, f"Method not found: {method}")


async def mcp_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
            status_code=400,
        )

    if isinstance(body, list):  # batch
        replies = [r for r in (handle_message(m, request.headers) for m in body) if r]
        if not replies:
            return Response(status_code=202)
        return JSONResponse(replies)

    reply = handle_message(body, request.headers)
    if reply is None:
        return Response(status_code=202)  # accepted, nothing to say back
    return JSONResponse(reply)


# The grader may be given either URL; both work.
app.add_api_route("/mcp", mcp_endpoint, methods=["POST"])
app.add_api_route("/", mcp_endpoint, methods=["POST"])


@app.get("/health")
def health():
    return {"status": "ok"}
