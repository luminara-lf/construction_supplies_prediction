from dataclasses import dataclass

from fastapi import Header, HTTPException


ALLOWED_ROLES = {"owner", "pm", "coordinator", "readonly"}


@dataclass(frozen=True)
class RequestContext:
    tenant_id: str
    user_id: str
    user_role: str


def get_request_context(
    x_tenant_id: str = Header(default="demo-tenant"),
    x_user_id: str = Header(default="demo-user"),
    x_user_role: str = Header(default="owner"),
) -> RequestContext:
    role = x_user_role.lower()
    if role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="Invalid x-user-role header.")
    return RequestContext(tenant_id=x_tenant_id, user_id=x_user_id, user_role=role)


def require_roles(ctx: RequestContext, *roles: str) -> None:
    if ctx.user_role not in roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions.")
