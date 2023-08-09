class FailedGameServerResponseError(Exception):
    """Raised when a game server command fails"""


class FailedGameServerCommandError(Exception):
    """Raised when out of reattempts"""


class AuthenticationError(Exception):
    """Raised when the game server fails for a login"""
