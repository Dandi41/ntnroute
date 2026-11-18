"""Newline-delimited JSON-RPC MCP subset. No approval issuance tool."""
import json

from .core import Error, canonical


SCHEMAS = {
    "profiles": {}, "capabilities": {},
    "inspect": {"device": "string", "profile": "string"},
    "plan": {"device": "string", "profile": "string", "action": "string", "params": "object", "recovery": "string"},
    "review": {"plan_id": "string"}, "apply": {"plan_id": "string"}, "rollback": {"plan_id": "string"},
}


def tools():
    return [{"name": name, "description": "NTnRoute " + name + "; vendor writes unsupported", "inputSchema": {"type": "object", "properties": {k: {"type": t} for k, t in fields.items()}, "required": list(fields), "additionalProperties": False}} for name, fields in SCHEMAS.items()]


def serve(core, source, sink):
    initialized = False
    while True:
        line = source.readline(65538)
        if not line:
            return
        request_id = None
        notification = False
        try:
            if len(line) > 65536:
                raise Error("request too large")
            request = json.loads(line)
            if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
                raise Error("invalid request")
            request_id = request.get("id")
            notification = "id" not in request
            if request_id is not None and (type(request_id) not in (str, int)):
                raise Error("invalid id")
            method = request.get("method")
            params = request.get("params", {})
            if not isinstance(params, dict):
                raise Error("invalid params")
            if notification:
                # Notifications cannot invoke tools or approve anything.
                continue
            if method == "initialize":
                initialized = True
                result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "ntn-web", "version": "0.1.0"}}
            elif method == "ping":
                result = {}
            elif not initialized:
                raise Error("initialize first")
            elif method == "tools/list":
                result = {"tools": tools()}
            elif method == "tools/call":
                name = params.get("name")
                args = params.get("arguments", {})
                if name not in SCHEMAS or not isinstance(args, dict) or set(args) != set(SCHEMAS[name]):
                    raise Error("unknown tool or invalid arguments")
                for key, kind in SCHEMAS[name].items():
                    if not isinstance(args[key], str if kind == "string" else dict):
                        raise Error("invalid argument type")
                result = {"content": [{"type": "text", "text": canonical(core.dispatch(name, args))}], "isError": False}
            else:
                raise Error("unknown method")
            response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as exc:
            # Never forward arbitrary exceptions/provider output, credentials or args.
            message = str(exc) if isinstance(exc, Error) else "invalid request or operation failed"
            response = {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": message}}
        if not notification:
            sink.write(canonical(response) + "\n")
            sink.flush()
        if len(line) > 65536:
            return
