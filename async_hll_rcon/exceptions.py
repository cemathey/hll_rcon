class FailedGameServerResponseError(Exception):
    """Raised when a game server command fails"""


class FailedGameServerCommandError(Exception):
    """Raised when out of reattempts"""
