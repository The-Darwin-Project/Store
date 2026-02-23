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


class AlertStatus(str, Enum):
    ACTIVE = "active"
    ORDERED = "ordered"
    DISMISSED = "dismissed"


class AlertType(str, Enum):
    RESTOCK = "restock"


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
    supplier_id: Optional[str] = None
    reorder_threshold: int = Field(default=10, ge=0)


class ProductCreate(BaseModel):
    """Schema for creating a new product."""
    name: str
    price: float = Field(ge=0)
    stock: int = Field(ge=0, default=0)
    sku: str
    image_data: Optional[str] = None
    description: Optional[str] = Field(default="")
    supplier_id: Optional[str] = None
    reorder_threshold: int = Field(default=10, ge=0)


class ProductUpdate(BaseModel):
    """Schema for partial product updates (PATCH). Only provided fields are applied."""
    name: Optional[str] = None
    price: Optional[float] = Field(default=None, ge=0)
    stock: Optional[int] = Field(default=None, ge=0)
    sku: Optional[str] = None
    image_data: Optional[str] = None
    description: Optional[str] = None
    supplier_id: Optional[str] = None
    reorder_threshold: Optional[int] = Field(default=None, ge=0)


class SupplierCreate(BaseModel):
    """Schema for creating a new supplier."""
    name: str
    contact_email: Optional[str] = None
    phone: Optional[str] = None


class Supplier(BaseModel):
    """Supplier schema for responses."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    contact_email: Optional[str] = None
    phone: Optional[str] = None
    created_at: Optional[datetime] = None


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
    coupon_code: Optional[str] = None


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
    coupon_code: Optional[str] = None
    discount_amount: float = 0.0


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


class Alert(BaseModel):
    """Alert schema for responses."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: AlertType = AlertType.RESTOCK
    message: str
    status: AlertStatus = AlertStatus.ACTIVE
    product_id: Optional[str] = None
    supplier_id: Optional[str] = None
    current_stock: Optional[int] = None
    reorder_threshold: Optional[int] = None
    created_at: Optional[datetime] = None


class AlertCreate(BaseModel):
    """Schema for creating a new alert."""
    type: AlertType = AlertType.RESTOCK
    message: str
    product_id: Optional[str] = None
    supplier_id: Optional[str] = None
    current_stock: Optional[int] = None
    reorder_threshold: Optional[int] = None


class AlertStatusUpdate(BaseModel):
    """Schema for updating alert status."""
    status: AlertStatus


class DiscountType(str, Enum):
    PERCENTAGE = "percentage"
    FIXED = "fixed"


class CouponCreate(BaseModel):
    """Schema for creating a new coupon."""
    code: str = Field(min_length=1, max_length=50)
    discount_type: DiscountType
    discount_value: float = Field(gt=0)
    min_order_amount: float = Field(default=0.0, ge=0)
    max_uses: int = Field(default=0, ge=0)  # 0 = unlimited
    expires_at: Optional[datetime] = None


class CouponUpdate(BaseModel):
    """Schema for partial coupon updates."""
    discount_type: Optional[DiscountType] = None
    discount_value: Optional[float] = Field(default=None, gt=0)
    min_order_amount: Optional[float] = Field(default=None, ge=0)
    max_uses: Optional[int] = Field(default=None, ge=0)
    expires_at: Optional[datetime] = None
    is_active: Optional[bool] = None


class Coupon(BaseModel):
    """Coupon schema for responses."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    code: str
    discount_type: DiscountType
    discount_value: float
    min_order_amount: float = 0.0
    max_uses: int = 0
    current_uses: int = 0
    is_active: bool = True
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class CouponValidateRequest(BaseModel):
    """Schema for validating a coupon against a cart total."""
    code: str
    cart_total: float = Field(gt=0)


class CouponValidationResult(BaseModel):
    """Result of coupon validation against a cart total."""
    valid: bool
    coupon: Optional[Coupon] = None
    discount_amount: float = 0.0
    final_total: float = 0.0
    error: Optional[str] = None
