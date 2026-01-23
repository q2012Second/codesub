"""Authentication service."""

from typing import Optional, Tuple
from datetime import datetime, timedelta


class AuthService:
    """Handles user authentication."""

    TOKEN_EXPIRY_HOURS = 24

    def __init__(self):
        self._sessions = {}

    def login(self, username: str, password: str) -> Optional[str]:
        """
        Authenticate user and return session token.
        Returns None if authentication fails.
        """
        # Simplified auth logic for demo
        if username and password:
            token = f"token_{username}_{datetime.now().timestamp()}"
            self._sessions[token] = {
                "username": username,
                "expires": datetime.now() + timedelta(hours=self.TOKEN_EXPIRY_HOURS)
            }
            return token
        return None

    def logout(self, token: str) -> bool:
        """Invalidate session token."""
        if token in self._sessions:
            del self._sessions[token]
            return True
        return False

    def validate_token(self, token: str) -> Tuple[bool, Optional[str]]:
        """
        Validate session token.
        Returns (is_valid, username).
        """
        session = self._sessions.get(token)
        if not session:
            return False, None
        if datetime.now() > session["expires"]:
            del self._sessions[token]
            return False, None
        return True, session["username"]

    def refresh_token(self, token: str) -> Optional[str]:
        """Refresh expiring token."""
        is_valid, username = self.validate_token(token)
        if is_valid and username:
            self.logout(token)
            return self.login(username, "refresh")
        return None
