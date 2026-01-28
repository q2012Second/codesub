# Java Order API Mock Repository

A sample e-commerce order management API in Java for demonstrating codesub's semantic subscription capabilities.

## Structure

```
src/main/java/com/example/orderapi/
├── config/
│   └── AppConfig.java           # Configuration constants
├── model/
│   ├── Order.java               # Order entity
│   ├── OrderItem.java           # Line item in an order
│   ├── OrderStatus.java         # Order lifecycle enum
│   ├── Product.java             # Catalog item
│   └── User.java                # Customer account
├── schema/
│   ├── api/                     # Public API contracts
│   │   ├── CreateOrderRequest.java
│   │   ├── CreateOrderResponse.java
│   │   ├── ErrorResponse.java
│   │   ├── OrderItemRequest.java
│   │   ├── OrderItemResponse.java
│   │   ├── OrderResponse.java
│   │   ├── PaginatedResponse.java
│   │   └── PricingBreakdown.java
│   └── external/                # External service schemas
│       ├── ShipFastAddress.java
│       ├── ShipFastShipment.java
│       ├── ShipFastTrackingEvent.java
│       ├── StripeCharge.java
│       ├── StripePaymentIntent.java
│       └── StripeWebhookEvent.java
├── service/
│   ├── OrderService.java        # Order processing logic
│   ├── OrderValidationException.java
│   ├── PaymentException.java
│   └── PaymentService.java      # Stripe integration
└── controller/
    └── OrderController.java     # REST endpoints
```

## Subscription Examples

### Configuration Constants

Track settings that affect business logic:

```bash
# API version - breaking changes indicator
codesub add "src/main/java/com/example/orderapi/config/AppConfig.java::AppConfig.API_VERSION" \
  --label "API version"

# Free shipping threshold
codesub add "src/main/java/com/example/orderapi/config/AppConfig.java::AppConfig.FREE_SHIPPING_THRESHOLD" \
  --label "Free shipping threshold"

# Tax rates by region
codesub add "src/main/java/com/example/orderapi/config/AppConfig.java::AppConfig.TAX_RATES" \
  --label "Tax rates"
```

### Business Logic

Track revenue-critical methods:

```bash
# Pricing calculation (critical!)
codesub add "src/main/java/com/example/orderapi/service/OrderService.java::OrderService.calculatePricing(List<OrderItem>,User)" \
  --label "Pricing calculation"

# Order validation rules
codesub add "src/main/java/com/example/orderapi/service/OrderService.java::OrderService.validateOrder(List<OrderItem>,User)" \
  --label "Order validation"
```

### Public API Schemas

Track API contracts that affect clients:

```bash
# Pricing breakdown total field
codesub add "src/main/java/com/example/orderapi/schema/api/PricingBreakdown.java::PricingBreakdown.total" \
  --label "Pricing total field"

# Order status in response
codesub add "src/main/java/com/example/orderapi/schema/api/OrderResponse.java::OrderResponse.status" \
  --label "Order status field"

# Error response format
codesub add "src/main/java/com/example/orderapi/schema/api/ErrorResponse.java::ErrorResponse.errorCode" \
  --label "Error code field"
```

### External API Contracts

Track external service schemas:

```bash
# Stripe payment status
codesub add "src/main/java/com/example/orderapi/schema/external/StripePaymentIntent.java::StripePaymentIntent.status" \
  --label "Stripe payment status"

# Stripe webhook event type
codesub add "src/main/java/com/example/orderapi/schema/external/StripeWebhookEvent.java::StripeWebhookEvent.type" \
  --label "Stripe webhook type"

# ShipFast tracking status
codesub add "src/main/java/com/example/orderapi/schema/external/ShipFastTrackingEvent.java::ShipFastTrackingEvent.status" \
  --label "ShipFast tracking status"
```

## Change Detection Examples

### CONTENT Change (Value Changed)

```java
// Before
public static final BigDecimal FREE_SHIPPING_THRESHOLD = new BigDecimal("75.00");

// After
public static final BigDecimal FREE_SHIPPING_THRESHOLD = new BigDecimal("100.00");
```
→ **CONTENT change** detected

### STRUCTURAL Change (Type/Signature Changed)

```java
// Before
private final BigDecimal total;

// After
private final double total;
```
→ **STRUCTURAL change** detected (type annotation changed)

### MISSING (Construct Deleted)

Delete the `validateOrder` method entirely.
→ **MISSING** detected

## Java Qualname Format

codesub uses overload-safe qualified names for Java:

| Construct | Format | Example |
|-----------|--------|---------|
| Class | `ClassName` | `OrderService` |
| Field | `Class.field` | `AppConfig.API_VERSION` |
| Method | `Class.method(ParamTypes)` | `OrderService.calculatePricing(List<OrderItem>,User)` |
| Constructor | `Class.Class(ParamTypes)` | `User.User(String,String,String)` |
| Enum constant | `Enum.CONSTANT` | `OrderStatus.PENDING` |

## Discovering Symbols

Use `codesub symbols` to explore available constructs:

```bash
# List all constructs in a file
codesub symbols src/main/java/com/example/orderapi/service/OrderService.java

# Filter by kind
codesub symbols src/main/java/com/example/orderapi/model/OrderStatus.java --kind field

# Search by name
codesub symbols src/main/java/com/example/orderapi/service/OrderService.java --grep pricing
```

Output:
```
Constructs in OrderService.java (8):

  class      OrderService
             Lines: 17-99
             FQN:   OrderService.java::OrderService

  field      OrderService.SHIPPING_RATE
             Lines: 19
             FQN:   OrderService.java::OrderService.SHIPPING_RATE

  method     OrderService.validateOrder(List,User)
             Lines: 24-39
             FQN:   OrderService.java::OrderService.validateOrder(List,User)

  method     OrderService.calculatePricing(List,User)
             Lines: 44-68
             FQN:   OrderService.java::OrderService.calculatePricing(List,User)
```
