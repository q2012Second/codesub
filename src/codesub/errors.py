"""Custom exceptions for codesub."""


class CodesubError(Exception):
    """Base exception for all codesub errors."""

    pass


class ConfigNotFoundError(CodesubError):
    """Raised when .codesub/subscriptions.json doesn't exist."""

    def __init__(self, path: str | None = None):
        self.path = path
        msg = "Config not initialized. Run 'codesub init' first."
        if path:
            msg = f"Config not found at {path}. Run 'codesub init' first."
        super().__init__(msg)


class ConfigExistsError(CodesubError):
    """Raised when trying to init but config already exists."""

    def __init__(self, path: str):
        self.path = path
        super().__init__(f"Config already exists at {path}. Use --force to overwrite.")


class InvalidSchemaVersionError(CodesubError):
    """Raised when config has an unsupported schema version."""

    def __init__(self, found: int, supported: int):
        self.found = found
        self.supported = supported
        super().__init__(
            f"Unsupported schema version {found}. This tool supports version {supported}."
        )


class SubscriptionNotFoundError(CodesubError):
    """Raised when a subscription ID doesn't exist."""

    def __init__(self, sub_id: str):
        self.sub_id = sub_id
        super().__init__(f"Subscription not found: {sub_id}")


class InvalidLocationError(CodesubError):
    """Raised when a location spec is invalid."""

    def __init__(self, location: str, reason: str | None = None):
        self.location = location
        msg = f"Invalid location: {location}"
        if reason:
            msg = f"{msg} ({reason})"
        super().__init__(msg)


class FileNotFoundAtRefError(CodesubError):
    """Raised when a file doesn't exist at the specified git ref."""

    def __init__(self, path: str, ref: str):
        self.path = path
        self.ref = ref
        super().__init__(f"File '{path}' not found at ref '{ref}'")


class GitError(CodesubError):
    """Raised when a git operation fails."""

    def __init__(self, command: str, stderr: str):
        self.command = command
        self.stderr = stderr
        super().__init__(f"Git command failed: {command}\n{stderr}")


class NotAGitRepoError(CodesubError):
    """Raised when not inside a git repository."""

    def __init__(self, path: str):
        self.path = path
        super().__init__(f"Not a git repository: {path}")


class InvalidLineRangeError(CodesubError):
    """Raised when line range is invalid."""

    def __init__(self, start: int, end: int, reason: str):
        self.start = start
        self.end = end
        super().__init__(f"Invalid line range {start}-{end}: {reason}")
