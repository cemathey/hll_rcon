from enum import StrEnum, IntEnum

RCON_PROTOCOL_VERSION = 2
RESPONSE_HEADER_SIZE = 8
HEADER_BIT_FORMAT = "<II"


class RconCommands(StrEnum):
    ADD_ADMIN = "AddAdmin"
    ADD_MAP_TO_ROTATION = "AddMapToRotation"
    ADD_MAP_TO_SEQUENCE = "AddMapToSequence"
    ADMIN_LOG = "AdminLog"
    AUTOBALANCE = "AutoBalance"
    AUTOBALANCE_THRESHOLD = "AutoBalanceThreshold"
    CHANGE_MAP = "ChangeMap"
    CHANGE_SECTOR_LAYOUT = "ChangeSectorLayout"
    CLIENT_REFERENCE_DATA = "ClientReferenceData"
    DISPLAYABLE_COMMANDS = "DisplayableCommands"
    KICK = "Kick"
    LOGIN = "Login"
    MESSAGE_PLAYER = "MessagePlayer"
    MOVE_MAP_IN_SEQUENCE = "MoveMapInSequence"
    PERMANENT_BAN = "PermanentBan"
    PUNISH_PLAYER = "PunishPlayer"
    REMOVE_ADMIN = "RemoveAdmin"
    REMOVE_MAP_FROM_ROTATION = "RemoveMapFromRotation"
    REMOVE_MAP_FROM_SEQUENCE = "RemoveMapFromSequence"
    REMOVE_PERMANENT_BAN = "RemovePermanentBan"
    REMOVE_TEMP_BAN = "RemoveTempBan"
    RESET_KICK_THRESHOLD = "ResetKickThreshold"
    SEND_SERVER_MESSAGE = "SendServerMessage"
    SERVER_BROADCAST = "ServerBroadcast"
    SERVER_INFORMATION = "ServerInformation"
    SET_HIGH_PING_THRESHOLD = "SetHighPingThreshold"
    SET_IDLE_KICK_DURATION = "SetIdleKickDuration"
    SET_MAX_QUEUED_PLAYERS = "SetMaxQueuedPlayers"
    SHUFFLE_MAP_SEQUENCE = "ShuffleMapSequence"
    TEAM_SWITCH_COOLDOWN = "TeamSwitchCooldown"
    TEMP_BAN = "TempBan"
    VOTE_KICK_ENABLED = "VoteKickEnabled"
    VOTE_KICK_THRESHOLD = "VoteKickThreshold"


class Platform(StrEnum):
    STEAM = "steam"
    WIN_GDK = "wingdk"
    EPIC = "eos"


# Similar to but distinct from HTTP status codes
class RconResponseStatusCode(IntEnum):
    """The game server status codes for requests

    Each response from the game server will contain one of these codes
    """

    OK = 200
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    SERVER_ERROR = 500


class ServerInformationCommands(StrEnum):
    """Valid content body names for the ServerInformation command"""

    PLAYERS = "players"
    PLAYER = "player"
    MAP_ROTATION = "maprotation"
    MAP_SEQUENCE = "mapsequence"
    SESSION = "session"
    SERVER_CONFIG = "serverconfig"


class Teams(IntEnum):
    GER = 0
    US = 1
    RUS = 2
    GB = 3
    DAK = 4
    B8A = 5
    NONE = 6
