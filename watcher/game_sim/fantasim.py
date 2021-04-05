from decimal import Decimal
from typing import Dict, Any

from watcher.game_sim.common import blood_id_map, fk_key, blood_name_map, Team, team_id_map, Weather, get_player_stlats, BloodType
from watcher.game_sim.game_state import GameState, InningHalf
from watcher.game_sim.team_state import DEF_ID, TeamState
from watcher.game_sim.common import ForbiddenKnowledge as FK
from watcher.game_sim.common import BlaseballStatistics as Stats, team_name_map

team_states: Dict[Team, TeamState] = {}

def get_stlat_dict(player: Dict[str, Any]) -> Dict[FK, float]:
    ret_val: Dict[FK, float] = {}
    for k in fk_key:
        str_name = fk_key[k]
        ret_val[k] = float(player[str_name])
    return ret_val


def load_state(team_id, season, day):
    team_info = {
        "lineup": {},
        "rotation": {},
        "blood": {},
        "game_stats": {},
        "segmented_stats": {},
        "stlats": {},
        "names": {}
    }
    player_stlats_list = get_player_stlats(season, day)
    for player in player_stlats_list:
        if day == 6 and player["team_id"] == "105bc3ff-1320-4e37-8ef0-8d595cb95dd0":
            x = 1
        if player["team_id"] != team_id:
            continue
        player_id = player["player_id"]
        pos = int(player["position_id"]) + 1
        if "position_type_id" in player:
            if player["position_type_id"] == "0":
                team_info["lineup"][pos] = player_id
            else:
                team_info["rotation"][pos] = player_id
        else:
            if player["position_type"] == "BATTER":
                team_info["lineup"][pos] = player_id
            else:
                team_info["rotation"][pos] = player_id
        team_info["stlats"][player_id] = get_stlat_dict(player)

        team_info["game_stats"][player_id] = {}
        team_info["game_stats"][DEF_ID] = {}

        team_info["segmented_stats"] = {}
        team_info["segmented_stats"] = {}

        team_info["names"][player_id] = player["player_name"]

        try:
            team_info["blood"][player_id] = blood_id_map[int(player["blood"])]
        except ValueError:
            team_info["blood"][player_id] = blood_name_map[player["blood"]]
        except TypeError:
            team_info["blood"][player_id] = BloodType.A
    return team_info

# s3 d1 wings
home_team = "57ec08cc-0411-4643-b304-0e80dbc15ac7"
h_team_pitcher = "089af518-e27c-4256-adc8-62e3f4b30f43"
#s14 d99 wings
away_team = "57ec08cc-0411-4643-b304-0e80dbc15ac7"
a_team_pitcher = "65273615-22d5-4df1-9a73-707b23e828d5"
h_team_season = 2
a_team_season = 13
h_team_day = 0
a_team_day = 98

team_info = load_state(home_team, h_team_season, h_team_day)
home_team_state = TeamState(
            team_id=home_team,
            season=h_team_season,
            day=h_team_season,
            weather=Weather.SUN2,
            is_home=True,
            num_bases=4,
            balls_for_walk=4,
            strikes_for_out=3,
            outs_for_inning=3,
            lineup=team_info["lineup"],
            rotation=team_info["rotation"],
            starting_pitcher=h_team_pitcher,
            cur_pitcher_pos=1,
            stlats=team_info["stlats"],
            game_stats=team_info["game_stats"],
            segmented_stats=team_info["segmented_stats"],
            blood=team_info["blood"],
            player_names=team_info["names"],
            cur_batter_pos=1,
            segment_size=1,
        )

team_info = load_state(away_team, a_team_season, a_team_day)
away_team_state = TeamState(
            team_id=away_team,
            season=a_team_season,
            day=a_team_season,
            weather=Weather.SUN2,
            is_home=True,
            num_bases=4,
            balls_for_walk=4,
            strikes_for_out=3,
            outs_for_inning=3,
            lineup=team_info["lineup"],
            rotation=team_info["rotation"],
            starting_pitcher=a_team_pitcher,
            cur_pitcher_pos=1,
            stlats=team_info["stlats"],
            game_stats=team_info["game_stats"],
            segmented_stats=team_info["segmented_stats"],
            blood=team_info["blood"],
            player_names=team_info["names"],
            cur_batter_pos=1,
            segment_size=1,
        )

game = GameState(
                game_id="1",
                season=0,
                day=0,
                home_team=home_team_state,
                away_team=away_team_state,
                home_score=Decimal("0"),
                away_score=Decimal("0"),
                inning=1,
                half=InningHalf.TOP,
                outs=0,
                strikes=0,
                balls=0,
                weather=Weather.SUN2
            )
iterations = 250
for x in range(0, iterations):
    game.simulate_game()
    game.reset_game_state()

home_win_count = home_team_state.game_stats[DEF_ID][Stats.TEAM_WINS]
print(f"{team_name_map[home_team_state.team_enum]} win: {home_win_count} "
      f"({home_win_count / iterations})")
