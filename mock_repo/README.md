# Mock Repository - Order Management API

A mock e-commerce order API demonstrating practical codesub subscription scenarios.

## Setup

```bash
task mock:init
```

This initializes git, registers the project, and creates sample subscriptions.

## Structure

```
mock_repo/
├── config.py              # App settings, external service URLs
├── models.py              # Domain models (User, Order, Product)
├── schemas/
│   ├── api.py             # Our public API request/response schemas
│   └── external.py        # External service response schemas
├── services/
│   ├── order.py           # Order processing, pricing calculation
│   └── payment.py         # Stripe payment integration
└── api/
    └── routes.py          # API endpoints
```

## What Gets Tracked

The `mock:init` task creates 11 subscriptions. Here's exactly what each one tracks:

### External API Contracts

When external providers change their API, our code breaks. Track their response schemas:

**Stripe payment status** (`schemas/external.py::StripePaymentIntent.status`):
```python
@dataclass
class StripePaymentIntent:
    ...
    status: str  # requires_payment_method, succeeded, etc.  <-- TRACKED
```

**Stripe webhook event type** (`schemas/external.py::StripeWebhookEvent.type`):
```python
@dataclass
class StripeWebhookEvent:
    ...
    type: str  # payment_intent.succeeded, payment_failed, etc.  <-- TRACKED
```

**Shipping tracking status** (`schemas/external.py::ShipFastTrackingEvent.status`):
```python
@dataclass
class ShipFastTrackingEvent:
    ...
    status: str  # in_transit, delivered, exception  <-- TRACKED
```

### Public API Schemas

Changes to these break frontend/mobile clients:

**Pricing total** (`schemas/api.py::PricingBreakdown.total`):
```python
@dataclass
class PricingBreakdown:
    subtotal: Decimal
    tax: Decimal
    shipping: Decimal
    total: Decimal  # <-- TRACKED: Frontend displays this
```

**Order status field** (`schemas/api.py::OrderResponse.status`):
```python
@dataclass
class OrderResponse:
    order_id: str
    status: str  # <-- TRACKED: Order status page uses this
    ...
```

### Business Logic

Revenue-critical code that needs review when changed:

**Pricing calculation** (`services/order.py::OrderService.calculate_pricing`):
```python
def calculate_pricing(self, items, user) -> PricingBreakdown:
    """Calculate order totals including tax and shipping."""
    subtotal = sum(item.subtotal for item in items)

    # Tax calculation based on user region
    tax_rate = TAX_RATES.get(user.region, TAX_RATES["DEFAULT"])
    tax = subtotal * Decimal(str(tax_rate))

    # Free shipping over threshold
    if subtotal >= Decimal(str(FREE_SHIPPING_THRESHOLD)):
        shipping = Decimal("0.00")
    else:
        shipping = self.SHIPPING_RATE
    ...
```

**Order validation** (`services/order.py::OrderService.validate_order`):
```python
def validate_order(self, items, user) -> None:
    """Validate order before creation."""
    if not items:
        raise OrderValidationError("Order must have at least one item")
    if len(items) > MAX_ORDER_ITEMS:
        raise OrderValidationError(f"Order cannot exceed {MAX_ORDER_ITEMS} items")
    ...
```

### Configuration

Settings that affect integrations and business rules:

**API version** (`config.py::API_VERSION`):
```python
API_VERSION = "v2"  # <-- TRACKED: Changing this is a breaking change
```

**Free shipping threshold** (`config.py::FREE_SHIPPING_THRESHOLD`):
```python
FREE_SHIPPING_THRESHOLD = 75.00  # <-- TRACKED: Affects pricing calculation
```

**Tax rates** (`config.py::TAX_RATES`):
```python
TAX_RATES = {
    "US-CA": 0.0725,
    "US-NY": 0.08,
    "US-TX": 0.0625,
    "EU": 0.20,
    "DEFAULT": 0.0,
}  # <-- TRACKED: Affects tax calculation
```

## Usage Examples

### List all subscriptions
```bash
codesub list
```

### Add a new subscription
```bash
# Track a specific field
codesub add "schemas/api.py::CreateOrderResponse.order_id" --label "Order ID format"

# Track a method
codesub add "services/payment.py::PaymentService.handle_webhook" --label "Webhook handler"

# Track a line range
codesub add "config.py:16-18" --label "Order limits"
```

### Discover trackable constructs
```bash
# List all constructs in a file
codesub symbols schemas/api.py

# Filter by kind
codesub symbols services/order.py --kind method

# Search by name
codesub symbols schemas/external.py --grep Stripe
```

### Scan for changes
```bash
# Scan after making changes
codesub scan

# Write update proposals to file
codesub scan --write-updates updates.json

# Apply proposed updates
codesub apply-updates updates.json
```

## Demo: Try It Yourself

After running `task mock:init`, make changes and scan:

### 1. Structural change (type modification)
```bash
# Edit schemas/api.py - change PricingBreakdown.total type:
#   total: Decimal  →  total: float

codesub scan
# Output: STRUCTURAL change detected (interface_hash changed)
```

### 2. Content change (logic modification)
```bash
# Edit config.py - change the threshold:
#   FREE_SHIPPING_THRESHOLD = 75.00  →  FREE_SHIPPING_THRESHOLD = 100.00

codesub scan
# Output: CONTENT change detected (body_hash changed)
```

### 3. Missing construct (deletion)
```bash
# Edit services/order.py - delete the validate_order method

codesub scan
# Output: MISSING - construct no longer exists
```

### 4. Rename detection
```bash
# Edit schemas/external.py - rename a field:
#   status: str  →  payment_status: str

codesub scan
# Output: Proposes update with rename detected
```

Run scans with: `task codesub:scan TARGET=mock_repo`
