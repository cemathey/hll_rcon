from datetime import datetime, timedelta

import pytest

from async_hll_rcon import constants
from async_hll_rcon.rcon import AsyncRcon
from async_hll_rcon.typedefs import (
    BanLogType,
    VipIdType,
    AdminGroupType,
    AdminIdType,
    ChatLogType,
    ConnectLogType,
    DisconnectLogType,
    KickLogType,
    KillLogType,
    LogTimeStampType,
    MatchEndLogType,
    MatchStartLogType,
    VoteKickThresholdType,
    PermanentBanType,
    BanLogBanType,
    PlayerInfoType,
    ScoreType,
    TeamKillLogType,
    TeamSwitchLogType,
    SquadType,
    TemporaryBanType,
    ServerPlayerSlotsType,
    GameStateType,
    PlayerNameType,
    SteamIdType,
)


@pytest.mark.parametrize(
    "items, expected",
    [
        (("some", "different", "words"), "some,different,words"),
    ],
)
def test_to_hll_list(items, expected):
    assert AsyncRcon._to_hll_list(items=items) == expected


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
def test_from_hll_list(raw, expected):
    assert AsyncRcon._from_hll_list(raw) == expected


@pytest.mark.parametrize(
    "slots, expected",
    [
        ("0/100", ServerPlayerSlotsType(current_players=0, max_players=100)),
    ],
)
def test_parse_get_current_max_player_slots(slots, expected):
    assert AsyncRcon._parse_get_current_max_player_slots(slots) == expected


@pytest.mark.parametrize(
    "gamestate, expected",
    [
        (
            """Players: Allied: 46 - Axis: 46
Score: Allied: 4 - Axis: 1
Remaining Time: 0:25:23
Map: carentan_offensive_ger
Next Map: hurtgenforest_warfare_V2""",
            GameStateType(
                allied_players=46,
                axis_players=46,
                allied_score=4,
                axis_score=1,
                remaining_time=timedelta(hours=0, minutes=25, seconds=23),
                current_map="carentan_offensive_ger",
                next_map="hurtgenforest_warfare_V2",
            ),
        ),
    ],
)
def test_parse_gamestate(gamestate, expected):
    assert AsyncRcon._parse_gamestate(gamestate) == expected


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
                ban_type=BanLogBanType.TEMPORARY_BAN,
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


@pytest.mark.parametrize(
    "raw_logs, expected",
    [
        (
            """[53.5 sec (1691524093)] KILL: JJ(Axis/76561199015319814) -> AceOfSpadess(Allies/76561197997173327) with MP40
[50.5 sec (1691524096)] TEAMSWITCH BakedBoi (None > Axis)
[49.1 sec (1691524097)] CHAT[Team][FreedomFries(Allies/76561198037148935)]: enemy garri destroyed B7k3""",
            (
                (
                    "KILL: JJ(Axis/76561199015319814) -> AceOfSpadess(Allies/76561197997173327) with MP40",
                    "53.5 sec",
                    "1691524093",
                ),
                ("TEAMSWITCH BakedBoi (None > Axis)", "50.5 sec", "1691524096"),
                (
                    "CHAT[Team][FreedomFries(Allies/76561198037148935)]: enemy garri destroyed B7k3",
                    "49.1 sec",
                    "1691524097",
                ),
            ),
        )
    ],
)
def test_split_raw_log_lines(raw_logs, expected):
    assert tuple(AsyncRcon.split_raw_log_lines(raw_logs)) == expected


@pytest.mark.parametrize(
    "name_and_ids, expected",
    [
        (
            [
                "Thunder_Chief : 76561198053381234",
                "Ispanky : 76561197984134321",
                "KidneyCarver : 76561197970731243",
            ],
            (
                {
                    "76561198053381234": PlayerNameType(name="Thunder_Chief"),
                    "76561197984134321": PlayerNameType(name="Ispanky"),
                    "76561197970731243": PlayerNameType(name="KidneyCarver"),
                },
                {
                    "Thunder_Chief": SteamIdType(steam_id_64="76561198053381234"),
                    "Ispanky": SteamIdType(steam_id_64="76561197984134321"),
                    "KidneyCarver": SteamIdType(steam_id_64="76561197970731243"),
                },
            ),
        )
    ],
)
def test_parse_get_player_steam_ids(name_and_ids, expected):
    assert AsyncRcon._parse_get_player_steam_ids(name_and_ids) == expected


@pytest.mark.parametrize(
    "raw_admin_id, expected",
    [
        (
            '76561198075923228 spectator "Grytzen"',
            AdminIdType(
                steam_id_64=SteamIdType(steam_id_64="76561198075923228"),
                role=AdminGroupType(role="spectator"),
                name=PlayerNameType(name="Grytzen"),
            ),
        ),
    ],
)
def test_parse_get_admin_ids(raw_admin_id, expected):
    assert AsyncRcon._parse_get_admin_id(raw_admin_id) == expected


@pytest.mark.parametrize(
    "vip_id, expected",
    [
        (
            '76561198042846962 "+Cronus+[DIXX] - (admin)"',
            VipIdType(
                steam_id_64=SteamIdType(steam_id_64="76561198042846962"),
                name="+Cronus+[DIXX] - (admin)",
            ),
        ),
        (
            '76561198214019848 "- RazBora - (BEER)"',
            VipIdType(
                steam_id_64=SteamIdType(steam_id_64="76561198214019848"),
                name="- RazBora - (BEER)",
            ),
        ),
    ],
)
def test_parse_get_vip_ids(vip_id, expected):
    assert AsyncRcon._parse_get_vip_id(vip_id) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            """Name: NoodleArms
steamID64: 76561198004123456
Team: Axis
Role: Assault
Unit: 8 - ITEM
Loadout: Standard Issue
Kills: 2 - Deaths: 2
Score: C 18, O 0, D 80, S 0
Level: 14
""",
            PlayerInfoType(
                player_name="NoodleArms",
                steam_id_64="76561198004123456",
                team="Axis",
                unit=SquadType(unit_id=8, unit_name="ITEM"),
                loadout="Standard Issue",
                role="Assault",
                score=ScoreType(
                    kills=2, deaths=2, combat=18, offensive=0, defensive=80, support=0
                ),
                level=14,
            ),
        )
    ],
)
def test_parse_player_info(raw, expected):
    assert AsyncRcon._parse_player_info(raw) == expected


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
    "raw_thresholds, expected",
    [
        (
            "0,1,10,5,25,12,50,20",
            [
                VoteKickThresholdType(player_count=0, votes_required=1),
                VoteKickThresholdType(player_count=10, votes_required=5),
                VoteKickThresholdType(player_count=25, votes_required=12),
                VoteKickThresholdType(player_count=50, votes_required=20),
            ],
        )
    ],
)
def test_parse_vote_kick_threshold(raw_thresholds, expected):
    assert AsyncRcon._parse_vote_kick_thresholds(raw_thresholds) == expected


@pytest.mark.parametrize(
    "raw, expected", [("1,2,3,4", "1,2,3,4"), ([(0, 1), (2, 3)], "0,1,2,3")]
)
def test_convert_vote_kick_thresholds(raw, expected):
    assert AsyncRcon._convert_vote_kick_thresholds(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1,2,3", ValueError),
        ((0,), ValueError),
        ("", ValueError),
        (None, ValueError),
        ("-1,1", ValueError),
        ("51,51", ValueError),
    ],
)
def test_convert_vote_kick_thresholds_exceptions(raw, expected):
    with pytest.raises(expected):
        AsyncRcon._convert_vote_kick_thresholds(raw)
