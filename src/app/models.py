# Store/src/app/models.py
# @ai-rules:
# 1. [Pattern]: Product schemas follow Create/Update/Read split -- ProductCreate for POST, ProductUpdate for PATCH, Product for responses.
# 2. [Constraint]: ProductUpdate fields must ALL be Optional to support partial updates via model_dump(exclude_unset=True).
# 3. [Gotcha]: Do not confuse Optional default=None with "field not sent". Use exclude_unset=True at call site.
"""Pydantic schemas for Darwin Store telemetry and product data."""

from pydantic import BaseModel, Field
from typing import Optional
from uuid import uuid4
from datetime import datetime
from enum import Enum


class OrderStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURNED = "returned"


# Valid transitions: current_status -> set of allowed next statuses
ORDER_STATUS_TRANSITIONS = {
    OrderStatus.PENDING: {OrderStatus.PROCESSING, OrderStatus.CANCELLED},
    OrderStatus.PROCESSING: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED, OrderStatus.CANCELLED},
    OrderStatus.DELIVERED: {OrderStatus.RETURNED},
    OrderStatus.CANCELLED: set(),   # terminal
    OrderStatus.RETURNED: set(),    # terminal
}


class OrderStatusUpdate(BaseModel):
    """Schema for updating order status."""
    status: OrderStatus


class Product(BaseModel):
    """Product schema for store inventory."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    price: float = Field(ge=0)
    stock: int = Field(ge=0, default=0)
    sku: str
    image_data: Optional[str] = None
    description: Optional[str] = Field(default="")


class ProductCreate(BaseModel):
    """Schema for creating a new product."""
    name: str
    price: float = Field(ge=0)
    stock: int = Field(ge=0, default=0)
    sku: str
    image_data: Optional[str] = None
    description: Optional[str] = Field(default="")


class ProductUpdate(BaseModel):
    """Schema for partial product updates (PATCH). Only provided fields are applied."""
    name: Optional[str] = None
    price: Optional[float] = Field(default=None, ge=0)
    stock: Optional[int] = Field(default=None, ge=0)
    sku: Optional[str] = None
    image_data: Optional[str] = None
    description: Optional[str] = None


class Customer(BaseModel):
    """Customer model."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    email: str
    created_at: Optional[datetime] = None


class CustomerCreate(BaseModel):
    """Schema for creating a new customer."""
    name: str
    email: str


class OrderItemCreate(BaseModel):
    """Schema for an item in an order creation request."""
    product_id: str
    quantity: int = Field(ge=1)


class OrderCreate(BaseModel):
    """Schema for creating a new order from cart items."""
    items: list[OrderItemCreate] = Field(min_length=1)
    customer_id: str


class OrderItem(BaseModel):
    """Schema for an order item in responses."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    order_id: str
    product_id: str
    quantity: int
    price_at_purchase: float


class Order(BaseModel):
    """Schema for an order in responses."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: Optional[datetime] = None
    total_amount: float
    status: str = "pending"
    items: list[OrderItem] = Field(default_factory=list)
    customer_id: Optional[str] = None


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


class GitOpsMetadata(BaseModel):
    """
    GitOps coordinates for self-describing services.
    
    Allows SysAdmin to discover where to make changes for this service.
    """
    repo: Optional[str] = Field(None, description="GitHub repo (e.g., 'The-Darwin-Project/Store')")
    repo_url: Optional[str] = Field(None, description="Full clone URL (e.g., 'https://github.com/The-Darwin-Project/Store.git')")
    helm_path: Optional[str] = Field(None, description="Path to Helm values.yaml within repo")


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
      },
      "gitops": {
        "repo": "The-Darwin-Project/Store",
        "helm_path": "helm/values.yaml"
      }
    }
    """
    service: str
    version: str
    metrics: Metrics
    topology: Topology = Field(default_factory=Topology)
    gitops: Optional[GitOpsMetadata] = Field(default=None, description="GitOps coordinates for this service")
    pod_ips: list[str] = Field(default_factory=list, description="Pod IP addresses for IP-to-name correlation")
