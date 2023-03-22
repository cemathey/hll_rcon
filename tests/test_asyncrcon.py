from datetime import datetime, timedelta

import pytest

from async_hll_rcon import constants
from async_hll_rcon.connection import HllConnection
from async_hll_rcon.rcon import AsyncRcon
from async_hll_rcon.typedefs import (
    BanLogType,
    ChatLogType,
    ConnectLogType,
    DisconnectLogType,
    KickLogType,
    KillLogType,
    LogTimeStampType,
    MatchEndLogType,
    MatchStartLogType,
    PermanentBanType,
    PlayerInfoType,
    ScoreType,
    TeamKillLogType,
    TeamSwitchLogType,
    TemporaryBanType,
)


@pytest.mark.parametrize("message, xor_key, expected", [("asdf", b"XOR", b"9<6>")])
def test_xor_encode(message, xor_key, expected):
    assert HllConnection._xor_encode(message, xor_key) == expected


@pytest.mark.parametrize("cipher_text, xor_key, expected", [(b"9<6>", b"XOR", "asdf")])
def test_xor_decode(cipher_text, xor_key, expected):
    assert HllConnection._xor_decode(cipher_text, xor_key) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("0\t", []),
        (
            "3\t\t\t",
            ["", "", ""],
        ),
        (
            '2\t76561198154123456 : banned for 48 hours on 2023.03.02-00.00.08 for "Homophobic text chat" by admin "-Scab"\t76561198090123456 : banned for 2 hours on 2023.03.02-16.22.01 for "Being a dick is in fact against the server rules." by admin "NoodleArms"\t',
            [
                '76561198154123456 : banned for 48 hours on 2023.03.02-00.00.08 for "Homophobic text chat" by admin "-Scab"',
                '76561198090123456 : banned for 2 hours on 2023.03.02-16.22.01 for "Being a dick is in fact against the server rules." by admin "NoodleArms"',
            ],
        ),
    ],
)
def test_list_conversion(raw, expected):
    assert AsyncRcon._from_hll_list(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            "2021.12.09-16.40.08",
            datetime(year=2021, month=12, day=9, hour=16, minute=40, second=8),
        )
    ],
)
def test_ban_list_timestamp_conversion(raw, expected):
    assert AsyncRcon._parse_ban_log_timestamp(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            '76561199023123456 : nickname "(WTH) Abu" banned for 2 hours on 2021.12.09-16.40.08 for "Being a troll" by admin "Some Admin Name"',
            TemporaryBanType(
                steam_id_64="76561199023123456",
                player_name="(WTH) Abu",
                duration_hours=2,
                timestamp=datetime(
                    year=2021, month=12, day=9, hour=16, minute=40, second=8
                ),
                reason="Being a troll",
                admin="Some Admin Name",
            ),
        ),
        (
            '76561199023123456 : banned for 2 hours on 2021.12.09-16.40.08 for "Being a troll" by admin "Some Admin Name"',
            TemporaryBanType(
                steam_id_64="76561199023123456",
                player_name=None,
                duration_hours=2,
                timestamp=datetime(
                    year=2021, month=12, day=9, hour=16, minute=40, second=8
                ),
                reason="Being a troll",
                admin="Some Admin Name",
            ),
        ),
    ],
)
def test_temp_ban_parsing(raw, expected):
    assert AsyncRcon._parse_temp_ban_log(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            '76561197975123456 : nickname "Georgij Zhukov Sovie" banned on 2022.12.06-16.27.14 for "Racism" by admin "BLACKLIST: NoodleArms"',
            PermanentBanType(
                steam_id_64="76561197975123456",
                player_name="Georgij Zhukov Sovie",
                timestamp=datetime(
                    year=2022, month=12, day=6, hour=16, minute=27, second=14
                ),
                reason="Racism",
                admin="BLACKLIST: NoodleArms",
            ),
        ),
        (
            '76561197975123456 : banned on 2022.12.06-16.27.14 for "Racism" by admin "BLACKLIST: NoodleArms"',
            PermanentBanType(
                steam_id_64="76561197975123456",
                player_name=None,
                timestamp=datetime(
                    year=2022, month=12, day=6, hour=16, minute=27, second=14
                ),
                reason="Racism",
                admin="BLACKLIST: NoodleArms",
            ),
        ),
    ],
)
def test_perma_ban_parsing(raw, expected):
    assert AsyncRcon._parse_perma_ban_log(raw) == expected


@pytest.mark.parametrize(
    "raw, expected", [("1,2,3,4", "1,2,3,4"), ([(0, 1), (2, 3)], "0,1,2,3")]
)
def test_convert_vote_kick_thresholds(raw, expected):
    assert AsyncRcon._convert_vote_kick_thresholds(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [("1,2,3", ValueError), ((0,), ValueError), ("", ValueError), (None, ValueError)],
)
def test_convert_vote_kick_thresholds_exceptions(raw, expected):
    with pytest.raises(expected):
        AsyncRcon._convert_vote_kick_thresholds(raw)


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            """Name: NoodleArms
steamID64: 76561198004123456
Team: None
Role: Rifleman
Kills: 0 - Deaths: 0
Score: C 0, O 0, D 0, S 0
Level: 238
""",
            PlayerInfoType(
                player_name="NoodleArms",
                steam_id_64="76561198004123456",
                team=None,
                role="Rifleman",
                score=ScoreType(
                    kills=0, deaths=0, combat=0, offensive=0, defensive=0, support=0
                ),
                level=238,
            ),
        )
    ],
)
def test_parse_player_info(raw, expected):
    assert AsyncRcon._parse_player_info(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1:00:43 hours", timedelta(hours=1, minutes=0, seconds=43)),
        ("1:43 min", timedelta(minutes=1, seconds=43)),
        ("58.5 sec", timedelta(seconds=58.5)),
        ("711 ms", timedelta(milliseconds=711)),
    ],
)
def test_relative_time_to_timedelta(raw, expected):
    assert AsyncRcon._relative_time_to_timedelta(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [("1678156382", datetime(year=2023, month=3, day=7, hour=2, minute=33, second=2))],
)
def test_absolute_time_to_datetime(raw, expected):
    assert AsyncRcon._absolute_time_to_datetime(raw) == expected


@pytest.mark.parametrize(
    "raw_log, relative_time, absolute_time, expected",
    [
        (
            "KILL: Code Red Dewd(Allies/76561197976123456) -> Beevus(Axis/76561198977123456) with BOMBING RUN",
            "1:07 min",
            "1678160118",
            KillLogType(
                steam_id_64="76561197976123456",
                player_name="Code Red Dewd",
                player_team="Allies",
                victim_steam_id_64="76561198977123456",
                victim_player_name="Beevus",
                victim_team="Axis",
                weapon="BOMBING RUN",
                time=LogTimeStampType(
                    absolute_timestamp=datetime(
                        year=2023, month=3, day=7, hour=3, minute=35, second=18
                    ),
                    relative_timestamp=timedelta(minutes=1, seconds=7),
                ),
            ),
        ),
        (
            "TEAM KILL: Code Red Dewd(Allies/76561197976123456) -> Beevus(Axis/76561198977123456) with BOMBING RUN",
            "1:07 min",
            "1678160118",
            TeamKillLogType(
                steam_id_64="76561197976123456",
                player_name="Code Red Dewd",
                player_team="Allies",
                victim_steam_id_64="76561198977123456",
                victim_player_name="Beevus",
                victim_team="Axis",
                weapon="BOMBING RUN",
                time=LogTimeStampType(
                    absolute_timestamp=datetime(
                        year=2023, month=3, day=7, hour=3, minute=35, second=18
                    ),
                    relative_timestamp=timedelta(minutes=1, seconds=7),
                ),
            ),
        ),
        (
            "CHAT[Team][Saucymuffin(Axis/76561198293123456)]: this server is pretty good",
            "1:07 min",
            "1678160118",
            ChatLogType(
                steam_id_64="76561198293123456",
                player_name="Saucymuffin",
                player_team="Axis",
                scope="Team",
                content="this server is pretty good",
                time=LogTimeStampType(
                    absolute_timestamp=datetime(
                        year=2023, month=3, day=7, hour=3, minute=35, second=18
                    ),
                    relative_timestamp=timedelta(minutes=1, seconds=7),
                ),
            ),
        ),
        (
            "CHAT[Unit][Saucymuffin(Axis/76561198293123456)]: this server is pretty good",
            "1:07 min",
            "1678160118",
            ChatLogType(
                steam_id_64="76561198293123456",
                player_name="Saucymuffin",
                player_team="Axis",
                scope="Unit",
                content="this server is pretty good",
                time=LogTimeStampType(
                    absolute_timestamp=datetime(
                        year=2023, month=3, day=7, hour=3, minute=35, second=18
                    ),
                    relative_timestamp=timedelta(minutes=1, seconds=7),
                ),
            ),
        ),
        (
            "CONNECTED Molotovgrl (76561198084123456)",
            "1:07 min",
            "1678160118",
            ConnectLogType(
                steam_id_64="76561198084123456",
                player_name="Molotovgrl",
                time=LogTimeStampType(
                    absolute_timestamp=datetime(
                        year=2023, month=3, day=7, hour=3, minute=35, second=18
                    ),
                    relative_timestamp=timedelta(minutes=1, seconds=7),
                ),
            ),
        ),
        (
            "DISCONNECTED BayouBanana (76561198084123456)",
            "1:07 min",
            "1678160118",
            DisconnectLogType(
                steam_id_64="76561198084123456",
                player_name="BayouBanana",
                time=LogTimeStampType(
                    absolute_timestamp=datetime(
                        year=2023, month=3, day=7, hour=3, minute=35, second=18
                    ),
                    relative_timestamp=timedelta(minutes=1, seconds=7),
                ),
            ),
        ),
        (
            "TEAMSWITCH Jack Burton (None > Allies)",
            "1:07 min",
            "1678160118",
            TeamSwitchLogType(
                player_name="Jack Burton",
                from_team="None",
                to_team="Allies",
                time=LogTimeStampType(
                    absolute_timestamp=datetime(
                        year=2023, month=3, day=7, hour=3, minute=35, second=18
                    ),
                    relative_timestamp=timedelta(minutes=1, seconds=7),
                ),
            ),
        ),
        (
            """BAN: [Scab Bucket] has been banned. [BANNED FOR 2 HOURS BY THE ADMINISTRATOR!
 Toxicity in command chat ]""",
            "1:07 min",
            "1678160118",
            BanLogType(
                player_name="Scab Bucket",
                ban_type=constants.TEMPORARY_BAN,
                ban_duration_hours=2,
                reason="Toxicity in command chat",
                time=LogTimeStampType(
                    absolute_timestamp=datetime(
                        year=2023, month=3, day=7, hour=3, minute=35, second=18
                    ),
                    relative_timestamp=timedelta(minutes=1, seconds=7),
                ),
            ),
        ),
        (
            """KICK: [Donny] has been kicked. [YOU WERE KICKED FOR BEING IDLE]""",
            "1:07 min",
            "1678160118",
            KickLogType(
                player_name="Donny",
                kick_type=constants.IDLE_KICK,
                reason="YOU WERE KICKED FOR BEING IDLE",
                time=LogTimeStampType(
                    absolute_timestamp=datetime(
                        year=2023, month=3, day=7, hour=3, minute=35, second=18
                    ),
                    relative_timestamp=timedelta(minutes=1, seconds=7),
                ),
            ),
        ),
        (
            "KICK: [dzkirandr] has been kicked. [Host closed the connection.]",
            "1:07 min",
            "1678160118",
            KickLogType(
                player_name="dzkirandr",
                kick_type=constants.HOST_CLOSED_CONNECTION_KICK,
                reason="Host closed the connection.",
                time=LogTimeStampType(
                    absolute_timestamp=datetime(
                        year=2023, month=3, day=7, hour=3, minute=35, second=18
                    ),
                    relative_timestamp=timedelta(minutes=1, seconds=7),
                ),
            ),
        ),
        (
            "KICK: [Daxter L Miller] has been kicked. [KICKED FOR TEAM KILLING!]",
            "1:07 min",
            "1678160118",
            KickLogType(
                player_name="Daxter L Miller",
                kick_type=constants.TEAM_KILLING_KICK,
                reason="KICKED FOR TEAM KILLING!",
                time=LogTimeStampType(
                    absolute_timestamp=datetime(
                        year=2023, month=3, day=7, hour=3, minute=35, second=18
                    ),
                    relative_timestamp=timedelta(minutes=1, seconds=7),
                ),
            ),
        ),
        (
            "MATCH ENDED `FOY WARFARE` ALLIED (1 - 4) AXIS",
            "1:07 min",
            "1678160118",
            MatchEndLogType(
                map_name="FOY",
                game_mode=constants.WARFARE_GAME_MODE,
                allied_score=1,
                axis_score=4,
                time=LogTimeStampType(
                    absolute_timestamp=datetime(
                        year=2023, month=3, day=7, hour=3, minute=35, second=18
                    ),
                    relative_timestamp=timedelta(minutes=1, seconds=7),
                ),
            ),
        ),
        (
            "MATCH START CARENTAN WARFARE",
            "1:07 min",
            "1678160118",
            MatchStartLogType(
                map_name="CARENTAN",
                game_mode=constants.WARFARE_GAME_MODE,
                time=LogTimeStampType(
                    absolute_timestamp=datetime(
                        year=2023, month=3, day=7, hour=3, minute=35, second=18
                    ),
                    relative_timestamp=timedelta(minutes=1, seconds=7),
                ),
            ),
        ),
    ],
)
def test_parse_game_log(raw_log, relative_time, absolute_time, expected):
    assert AsyncRcon._parse_game_log(raw_log, relative_time, absolute_time) == expected
