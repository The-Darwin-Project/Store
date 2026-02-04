# Store/src/app/models.py
"""Pydantic schemas for Darwin Store telemetry and product data."""

from pydantic import BaseModel, Field
from typing import Optional
from uuid import uuid4


class Product(BaseModel):
    """Product schema for store inventory."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    price: float = Field(ge=0)
    stock: int = Field(ge=0, default=0)


class ProductCreate(BaseModel):
    """Schema for creating a new product."""
    name: str
    price: float = Field(ge=0)
    stock: int = Field(ge=0, default=0)


class Dependency(BaseModel):
    """Topology dependency - represents a service this app connects to."""
    target: str  # Service name or hostname
    type: str    # "db" or "http"
    env_var: str  # The env var KEY name (e.g., DATABASE_URL)


class Topology(BaseModel):
    """
    Topology structure matching DESIGN.md schema.
    
    Schema from DESIGN.md:
    "topology": {
      "dependencies": [
        { "target": "postgres-primary", "type": "db", "env_var": "DB_HOST" }
      ]
    }
    """
    dependencies: list[Dependency] = Field(default_factory=list)


class Metrics(BaseModel):
    """Runtime metrics for telemetry."""
    cpu: float = Field(ge=0, le=100)
    memory: float = Field(ge=0, le=100)
    error_rate: float = Field(ge=0, le=100)


class TelemetryPayload(BaseModel):
    """
    Full telemetry payload sent to Darwin BlackBoard.
    
    Matches DESIGN.md schema:
    {
      "service": "inventory-api",
      "version": "v2.0",
      "metrics": { "cpu": 95.0, "error_rate": 0.12 },
      "topology": {
        "dependencies": [
          { "target": "postgres-primary", "type": "db", "env_var": "DB_HOST" }
        ]
      }
    }
    """
    service: str
    version: str
    metrics: Metrics
    topology: Topology = Field(default_factory=Topology)
