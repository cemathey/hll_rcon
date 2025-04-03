from enum import StrEnum, IntEnum

RCON_PROTOCOL_VERSION = 2
RESPONSE_HEADER_SIZE = 8
HEADER_BIT_FORMAT = "<II"


class RconCommands(StrEnum):
    """Models the discoverable RCON commands

    Each individual discoverable command can be queried with `ClientReferenceData`
    and the command name to obtain valid parameters and their types
    """

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


class ClientReferenceDataParameterType(StrEnum):
    COMBO = "combo"
    NUMBER = "number"
    TEXT = "text"


class ServerInformationCommands(StrEnum):
    """Valid content body names for the ServerInformation command"""

    PLAYERS = "players"
    PLAYER = "player"
    MAP_ROTATION = "maprotation"
    MAP_SEQUENCE = "mapsequence"
    SESSION = "session"
    SERVER_CONFIG = "serverconfig"


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


class MapOrientations(StrEnum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class MapEnvironments(StrEnum):
    DAWN = "dawn"
    DAY = "day"
    DUSK = "dusk"
    NIGHT = "night"
    OVERCAST = "overcast"
    RAIN = "rain"


class GameMode(StrEnum):
    WARFARE = "warfare"
    OFFENSIVE = "offensive"
    CONTROL = "control"


class Teams(StrEnum):
    AXIS = "axis"
    ALLIES = "allies"


class Factions(IntEnum):
    GER = 0
    US = 1
    RUS = 2
    GB = 3
    DAK = 4
    B8A = 5
    NONE = 6


MAP_COLUMNS = "ABCDEFGHIJ"

# Conversion factors to let us write in meters since player position
# is reported by the game server in centimeters
CM_TO_METERS = 100.0
METERS_TO_CM = 0.01

GridCoordinate = tuple[float, float]
ORIGIN: GridCoordinate = (0.0, 0.0)
H_MAX_X = 1000 * CM_TO_METERS
H_MAX_Y = 600 * CM_TO_METERS
V_MAX_X = 600 * CM_TO_METERS
V_MAX_Y = 1000 * CM_TO_METERS


class MapColumns(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    F = "F"
    G = "G"
    H = "H"
    I = "I"
    J = "J"
