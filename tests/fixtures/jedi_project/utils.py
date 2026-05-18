from models import User


def get_user_display(user: User) -> str:
    """Format user for display."""
    return f"{user.name} <{user.email}>"


def validate_email(email: str) -> bool:
    """Check if email is valid."""
    return "@" in email
