from typing import Any, Optional, List
from pydantic import BaseModel


class WorkflowCreate(BaseModel):
    name: str
    description: Optional[str] = None
    graph: Optional[Any] = None


class WorkflowOut(BaseModel):
    id: int
    workspace_id: int
    name: str
    description: Optional[str] = None
    graph: Optional[Any] = None
    version: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        orm_mode = True


class RunLogOut(BaseModel):
    id: int
    run_id: int
    node_id: Optional[str] = None
    timestamp: Optional[str] = None
    level: Optional[str] = None
    message: Optional[str] = None

    class Config:
        orm_mode = True


class RunOut(BaseModel):
    id: int
    workflow_id: int
    status: str
    input_payload: Optional[Any] = None
    output_payload: Optional[Any] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    attempts: Optional[int] = 0

    class Config:
        orm_mode = True


class RunDetail(RunOut):
    logs: Optional[List[RunLogOut]] = []

    class Config:
        orm_mode = True


class LogsResponse(BaseModel):
    logs: List[RunLogOut]

    class Config:
        orm_mode = True


class RunsPage(BaseModel):
    items: List[RunOut]
    total: int
    limit: int
    offset: int

    class Config:
        orm_mode = True


class SecretCreate(BaseModel):
    name: str
    value: str


class SecretOut(BaseModel):
    id: int
    workspace_id: int
    name: str
    created_by: int
    created_at: Optional[str]

    class Config:
        orm_mode = True


class ProviderCreate(BaseModel):
    type: str
    config: Optional[Any] = None
    # Optional secret_id may be provided to reference an existing Secret
    secret_id: Optional[int] = None


class ProviderOut(BaseModel):
    id: int
    workspace_id: int
    type: str
    secret_id: Optional[int] = None
    created_at: Optional[str]

    class Config:
        orm_mode = True
