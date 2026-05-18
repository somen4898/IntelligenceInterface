class User:
    """A user entity."""

    def __init__(self, name: str, email: str):
        self.name = name
        self.email = email

    def save(self) -> bool:
        """Persist the user to storage."""
        return True

    def delete(self) -> bool:
        """Remove the user from storage."""
        return True


class Product:
    """A product entity."""

    def __init__(self, title: str, price: float):
        self.title = title
        self.price = price

    def save(self) -> bool:
        """Persist the product to storage."""
        return True
