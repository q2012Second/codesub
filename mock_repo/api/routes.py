"""API route definitions."""

from typing import Dict, List, Any


# Route registry
ROUTES: Dict[str, Dict[str, Any]] = {}


def route(path: str, methods: List[str] = None):
    """Decorator to register API routes."""
    def decorator(func):
        ROUTES[path] = {
            "handler": func,
            "methods": methods or ["GET"]
        }
        return func
    return decorator


@route("/users", methods=["GET"])
def list_users() -> Dict:
    """List all users."""
    return {"users": [], "count": 0}


@route("/users/<id>", methods=["GET"])
def get_user(id: int) -> Dict:
    """Get user by ID."""
    return {"user": None}


@route("/users", methods=["POST"])
def create_user(data: Dict) -> Dict:
    """Create new user."""
    return {"user": data, "id": 1}


@route("/products", methods=["GET"])
def list_products() -> Dict:
    """List all products."""
    return {"products": [], "count": 0}


@route("/orders", methods=["GET", "POST"])
def orders(data: Dict = None) -> Dict:
    """Handle orders endpoint."""
    if data:
        return {"order": data, "id": 1}
    return {"orders": [], "count": 0}


@route("/health", methods=["GET"])
def health_check() -> Dict:
    """Health check endpoint."""
    return {"status": "healthy", "version": "1.0.0"}
