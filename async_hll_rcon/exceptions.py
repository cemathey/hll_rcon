class FailedGameServerResponse(Exception):
    """Raised when a game server command fails"""


class FailedGameServerCommand(Exception):
    """Raised when out of reattempts"""
