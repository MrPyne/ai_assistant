from datetime import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, JSON, DateTime
from sqlalchemy.orm import relationship
from .database import Base

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    # role field used for simple RBAC (e.g., 'user' or 'admin'). Default
    # remains 'user' for existing behaviour.
    role = Column(String, default='user')
    workspaces = relationship('Workspace', back_populates='owner')

class Workspace(Base):
    __tablename__ = 'workspaces'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    owner_id = Column(Integer, ForeignKey('users.id'))
    owner = relationship('User', back_populates='workspaces')

class Secret(Base):
    __tablename__ = 'secrets'
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey('workspaces.id'))
    name = Column(String, nullable=False)
    encrypted_value = Column(String, nullable=False)
    created_by = Column(Integer, ForeignKey('users.id'))
    created_at = Column(DateTime, default=datetime.utcnow)

class Provider(Base):
    __tablename__ = 'providers'
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey('workspaces.id'))
    # reference to Secret.id for provider credentials (preferred)
    secret_id = Column(Integer, ForeignKey('secrets.id'), nullable=True)
    type = Column(String, nullable=False)
    config = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

class Workflow(Base):
    __tablename__ = 'workflows'
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey('workspaces.id'))
    name = Column(String, nullable=False)
    description = Column(String)
    graph = Column(JSON)
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

class Run(Base):
    __tablename__ = 'runs'
    id = Column(Integer, primary_key=True)
    workflow_id = Column(Integer, ForeignKey('workflows.id'))
    status = Column(String, default='pending')
    input_payload = Column(JSON)
    output_payload = Column(JSON)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    # number of attempts made executing this run
    attempts = Column(Integer, default=0)

class RunLog(Base):
    __tablename__ = 'run_logs'
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey('runs.id'))
    node_id = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    level = Column(String, default='info')
    message = Column(String)


class Webhook(Base):
    __tablename__ = 'webhooks'
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey('workspaces.id'))
    workflow_id = Column(Integer, ForeignKey('workflows.id'))
    path = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey('workspaces.id'), nullable=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    action = Column(String, nullable=False)
    object_type = Column(String, nullable=True)
    object_id = Column(Integer, nullable=True)
    detail = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
