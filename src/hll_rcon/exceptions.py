class HLLAuthError(Exception):
    """Raised if the RCON password is incorrect (401)"""


class HLLBadCommand(Exception):
    """Raised if the server response is 400"""


class HLLGameServerError(Exception):
    """Raised if the server response is 500"""
