# @ai-rules:
# 1. [Pattern]: Customer schemas follow Create/Update/Read split.
# 2. [Constraint]: CustomerUpdate fields must ALL be Optional to support partial updates.
"""Pydantic schemas for Customer Management Service domain models."""

from pydantic import BaseModel, Field
from typing import Generic, Optional, TypeVar
from uuid import uuid4
from datetime import datetime
from enum import Enum


T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard paginated response envelope."""
    items: list[T]
    total: int
    page: int
    limit: int
    pages: int


class OrderStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURNED = "returned"


ORDER_STATUS_TRANSITIONS = {
    OrderStatus.PENDING: {OrderStatus.PROCESSING, OrderStatus.CANCELLED},
    OrderStatus.PROCESSING: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED, OrderStatus.CANCELLED},
    OrderStatus.DELIVERED: {OrderStatus.RETURNED},
    OrderStatus.CANCELLED: set(),
    OrderStatus.RETURNED: set(),
}


class OrderStatusUpdate(BaseModel):
    """Schema for updating order status."""
    status: OrderStatus


class CustomerCreate(BaseModel):
    """Schema for creating a new customer."""
    name: str
    email: str
    company: Optional[str] = None
    phone: Optional[str] = None
    shipping_street: Optional[str] = None
    shipping_city: Optional[str] = None
    shipping_state: Optional[str] = None
    shipping_zip: Optional[str] = None
    shipping_country: Optional[str] = None


class CustomerUpdate(BaseModel):
    """Schema for partial customer updates."""
    name: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    phone: Optional[str] = None
    shipping_street: Optional[str] = None
    shipping_city: Optional[str] = None
    shipping_state: Optional[str] = None
    shipping_zip: Optional[str] = None
    shipping_country: Optional[str] = None


class Customer(BaseModel):
    """Customer model."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    email: str
    company: Optional[str] = None
    phone: Optional[str] = None
    shipping_street: Optional[str] = None
    shipping_city: Optional[str] = None
    shipping_state: Optional[str] = None
    shipping_zip: Optional[str] = None
    shipping_country: Optional[str] = None
    created_at: Optional[datetime] = None


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
    product_name: Optional[str] = None


class Order(BaseModel):
    """Schema for an order in responses."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: Optional[datetime] = None
    total_amount: float
    status: str = "pending"
    items: list[OrderItem] = Field(default_factory=list)
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    coupon_code: Optional[str] = None
    discount_amount: float = 0.0
    invoice_id: Optional[str] = None


class InvoiceLineItem(BaseModel):
    """A single line item in an invoice."""
    product_name: str
    sku: str
    unit_price: float
    quantity: int
    line_total: float


class CustomerSnapshot(BaseModel):
    """Customer data frozen at invoice generation time."""
    name: str
    email: str
    company: Optional[str] = None
    phone: Optional[str] = None
    shipping_street: Optional[str] = None
    shipping_city: Optional[str] = None
    shipping_state: Optional[str] = None
    shipping_zip: Optional[str] = None
    shipping_country: Optional[str] = None


class Invoice(BaseModel):
    """Invoice schema for responses."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    invoice_number: int
    order_id: str
    customer_snapshot: CustomerSnapshot
    line_items: list[InvoiceLineItem]
    subtotal: float
    coupon_code: Optional[str] = None
    discount_amount: float = 0.0
    grand_total: float
    created_at: Optional[datetime] = None
