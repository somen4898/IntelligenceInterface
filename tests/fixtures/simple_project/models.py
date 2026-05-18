"""Data models for the application."""

from dataclasses import dataclass


@dataclass
class User:
    """A user in the system."""
    name: str
    email: str

    def save(self) -> None:
        """Persist the user."""
        pass

    def delete(self) -> None:
        """Remove the user."""
        pass


@dataclass
class Product:
    """A product listing."""
    title: str
    price: float

    def save(self) -> None:
        """Persist the product."""
        pass


MAX_USERS = 100
