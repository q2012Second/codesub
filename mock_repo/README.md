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

## Subscription Examples

The mock:init task creates subscriptions demonstrating real-world use cases:

### External API Contracts
Track schemas for external services. If they change their API, we need to know:

| Target | Why Track |
|--------|-----------|
| `schemas/external.py::StripePaymentIntent.status` | Payment status determines order flow |
| `schemas/external.py::StripeWebhookEvent.type` | Webhook event routing |
| `schemas/external.py::ShipFastTrackingEvent.status` | Shipping status updates |

### Public API Schemas
Track our API contracts. Changes here break client integrations:

| Target | Why Track |
|--------|-----------|
| `schemas/api.py::PricingBreakdown.total` | Frontend displays this to users |
| `schemas/api.py::OrderResponse.status` | Order status page depends on this |
| `schemas/api.py::ErrorResponse.error_code` | Client error handling |

### Critical Business Logic
Track code that affects revenue and correctness:

| Target | Why Track |
|--------|-----------|
| `services/order.py::OrderService.calculate_pricing` | Pricing calculation affects revenue |
| `services/order.py::OrderService.validate_order` | Validation rules affect UX |

### Configuration
Track settings that affect business logic:

| Target | Why Track |
|--------|-----------|
| `config.py::API_VERSION` | Breaking change for API clients |
| `config.py::FREE_SHIPPING_THRESHOLD` | Affects shipping cost calculation |
| `config.py::TAX_RATES` | Affects tax calculation |

## Demo Scenarios

After `task mock:init`, try these changes and run `task codesub:scan TARGET=mock_repo`:

1. **Change API response field type** - Change `PricingBreakdown.total` from `Decimal` to `float`:
   - Detects STRUCTURAL change in API schema

2. **Modify pricing logic** - Change the shipping calculation in `calculate_pricing`:
   - Detects CONTENT change in business logic

3. **Update config value** - Change `FREE_SHIPPING_THRESHOLD` from 75.00 to 100.00:
   - Detects CONTENT change in configuration

4. **Delete a tracked method** - Remove `validate_order` method:
   - Detects MISSING construct
