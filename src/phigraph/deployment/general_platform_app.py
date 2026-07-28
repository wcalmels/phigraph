from typing import Any
import pandas as pd
from fastapi import APIRouter,Header,HTTPException
from pydantic import BaseModel,Field
from phigraph.platform import authorize
from phigraph.platform_general import GeneralPlatformRuntime
from .auth import principal_from_headers
class DomainPrepareRequest(BaseModel):
    domain:str; tables:dict[str,list[dict[str,Any]]]; requested_action:str|None=None
    mode:str=Field(default="advisory",pattern="^(advisory|sandbox)$")
def create_general_platform_router():
    router=APIRouter(prefix="/v2/domains",tags=["domains"]); runtime=GeneralPlatformRuntime()
    @router.get("")
    def list_domains(x_subject:str|None=Header(default=None),x_roles:str|None=Header(default=None)):
        p=principal_from_headers(x_subject,x_roles)
        if not authorize(p,"registry:read"): raise HTTPException(403,"Forbidden.")
        return runtime.registry.list()
    @router.post("/prepare")
    def prepare(req:DomainPrepareRequest,x_subject:str|None=Header(default=None),x_roles:str|None=Header(default=None)):
        p=principal_from_headers(x_subject,x_roles)
        if not authorize(p,"shadow:run"): raise HTTPException(403,"Forbidden.")
        try:
            return runtime.prepare(domain=req.domain,tables={k:pd.DataFrame(v) for k,v in req.tables.items()},
                requested_action=req.requested_action,mode=req.mode).to_dict()
        except KeyError as e: raise HTTPException(404,str(e))
    return router
