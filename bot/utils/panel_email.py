PANEL_EMAIL_PREFIX = "user_"


def get_panel_email_prefix(user: dict) -> str:
    """Returns the common email prefix of the client in the 3X-UI panel."""
    if user.get('username'):
        return f"{PANEL_EMAIL_PREFIX}{user['username']}_"
    return f"{PANEL_EMAIL_PREFIX}{user['telegram_id']}_"


def is_managed_panel_email(email: object) -> bool:
    """Return whether a panel client identifier belongs to the bot."""
    if not isinstance(email, str):
        return False
    return email.strip().casefold().startswith(PANEL_EMAIL_PREFIX)


__all__ = [
    "PANEL_EMAIL_PREFIX",
    "get_panel_email_prefix",
    "is_managed_panel_email",
]
