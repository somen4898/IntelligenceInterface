from models import User, Product


def create_user(name: str, email: str) -> User:
    """Create and save a new user."""
    user = User(name=name, email=email)
    user.save()
    return user


def delete_user(user: User) -> bool:
    """Delete an existing user."""
    return user.delete()


def create_product(title: str, price: float) -> Product:
    """Create and save a new product."""
    product = Product(title=title, price=price)
    product.save()
    return product
