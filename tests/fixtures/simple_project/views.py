"""View handlers."""

from models import User, Product


def get_user(user_id: int) -> User:
    """Fetch a user by ID."""
    return User(name="test", email="test@test.com")


def list_products() -> list[Product]:
    """List all products."""
    return []


async def async_handler(request) -> dict:
    """An async view handler."""
    user = get_user(request.user_id)
    return {"user": user.name}
