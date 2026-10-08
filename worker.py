import httpx
from pydantic import BaseModel, Field
from typing import Any, Optional, List
import mistralai.workflows as workflows

class OdooClient:
    def __init__(self, url, db, login, api_key):
        self.base = url.rstrip("/")
        self.db, self.login, self.api_key = db, login, api_key
        self.uid = None
        self.http = httpx.Client(timeout=60)

    def _rpc(self, service, method, args):
        payload = {"jsonrpc": "2.0", "method": "call",
                   "params": {"service": service, "method": method, "args": args},
                   "id": "odoo-bridge"}
        data = self.http.post(self.base + "/jsonrpc", json=payload).json()
        if "error" in data:
            raise RuntimeError("Odoo error: " + str(data["error"].get("data", data["error"])))
        return data.get("result")

    def execute_kw(self, model, method, args, kwargs):
        if not self.uid:
            self.uid = self._rpc("common", "authenticate", [self.db, self.login, self.api_key, {}])
            if not self.uid:
                raise RuntimeError("Odoo authentication failed")
        return self._rpc("object", "execute_kw", [self.db, self.uid, self.api_key, model, method, args, kwargs])

class OdooCallInput(BaseModel):
    url: str
    db: str
    login: str
    api_key: str
    model: str
    operation: str
    domain: Optional[list] = []
    fields: Optional[list] = None
    limit: Optional[int] = None
    offset: Optional[int] = None
    order: Optional[str] = None
    ids: Optional[List[int]] = None
    values: Optional[dict] = None
    method: Optional[str] = None
    args: Optional[list] = None
    kwargs: Optional[dict] = None

@workflows.activity()
async def run_odoo_operation(input_data: dict) -> dict:
    inp = OdooCallInput(**input_data)
    c = OdooClient(inp.url, inp.db, inp.login, inp.api_key)
    op = inp.operation
    if op == "search_read":
        kw = {"domain": inp.domain or []}
        if inp.fields: kw["fields"] = inp.fields
        if inp.limit: kw["limit"] = inp.limit
        if inp.offset: kw["offset"] = inp.offset
        if inp.order: kw["order"] = inp.order
        return {"result": c.execute_kw(inp.model, "search_read", [], kw)}
    if op == "search":
        return {"result": c.execute_kw(inp.model, "search", [inp.domain or []], {})}
    if op == "read":
        return {"result": c.execute_kw(inp.model, "read", [inp.ids or []], {"fields": inp.fields or []})}
    if op == "create":
        return {"result": c.execute_kw(inp.model, "create", [inp.values or {}], {})}
    if op == "write":
        return {"result": c.execute_kw(inp.model, "write", [inp.ids or [], inp.values or {}], {})}
    if op == "unlink":
        return {"result": c.execute_kw(inp.model, "unlink", [inp.ids or []], {})}
    if op == "fields_get":
        return {"result": c.execute_kw(inp.model, "fields_get", [], {"attributes": ["string", "type", "relation"]})}
    if op == "call":
        if not inp.method:
            raise RuntimeError("operation=call requires 'method'")
        return {"result": c.execute_kw(inp.model, inp.method, inp.args or [], inp.kwargs or {})}
    raise RuntimeError("Unknown operation: " + op)

@workflows.workflow.define(
    name="odoo-call",
    workflow_display_name="Odoo Call",
    workflow_description="Operation generique sur Odoo via JSON-RPC, sans code dans Odoo.",
)
class OdooCallWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, input: OdooCallInput) -> dict:
        return await run_odoo_operation(input.model_dump())

if __name__ == "__main__":
    workflows.run_worker([OdooCallWorkflow])
