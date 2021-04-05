from decimal import Decimal
from typing import Any, Dict, List, Tuple
import json
import logging
import statistics

from watcher.game_sim.common import BlaseballStatistics as Stats
from watcher.game_sim.common import ForbiddenKnowledge as FK
from watcher.game_sim.common import AdditiveTypes, BloodType, calc_vibes, GameEventTeamBuff, PlayerBuff, \
    Team, team_game_event_map, team_id_map, Weather
from watcher.game_sim.stadium import Stadium

DEF_ID = "DEFENSE"
TEAM_ID = "TEAM"


class TeamState(object):
    def __init__(
        self,
        team_id: str,
        season: int,
        day: int,
        stadium: Stadium,
        weather: Weather,
        is_home: bool,
        num_bases: int,
        balls_for_walk: int,
        strikes_for_out: int,
        outs_for_inning: int,
        lineup: Dict[int, str],
        rotation: Dict[int, str],
        starting_pitcher: str,
        cur_pitcher_pos: int,
        stlats: Dict[str, Dict[FK, float]],
        buffs: Dict[str, Dict[PlayerBuff, int]],
        game_stats: Dict[str, Dict[Stats, float]],
        segmented_stats: Dict[int, Dict[str, Dict[Stats, float]]],
        blood: Dict[str, BloodType],
        player_names: Dict[str, str],
        cur_batter_pos: int,
        segment_size: int = 3
    ) -> None:
        """ A container class that holds the team state for a given game """
        self.team_id: str = team_id
        self.team_enum: Team = team_id_map[team_id]
        self.season: int = season
        self.day: int = day
        self.stadium = stadium
        self.weather: Weather = weather
        self.is_home: bool = is_home
        self.runners_aboard: bool = False
        self.num_bases: int = num_bases
        self.balls_for_walk: int = balls_for_walk
        self.strikes_for_out: int = strikes_for_out
        self.outs_for_inning: int = outs_for_inning
        self.lineup: Dict[int, str] = lineup
        self.rotation: Dict[int, str] = rotation
        self.starting_pitcher: str = starting_pitcher
        self.cur_pitcher_pos: int = cur_pitcher_pos
        self.stlats: Dict[str, Dict[FK, float]] = stlats
        self.player_buffs: Dict[str, Dict[PlayerBuff, int]] = buffs
        self.game_stats: Dict[str, Dict[Stats, float]] = game_stats
        self.segmented_stats: Dict[int, Dict[str, Dict[Stats, float]]] = segmented_stats
        self.segment_size = segment_size
        self.blood: Dict[str, BloodType] = blood
        self.player_names: Dict[str, str] = player_names
        self.cur_batter_pos: int = cur_batter_pos
        self.cur_batter: str = lineup[cur_batter_pos]
        self.batting_addition: float = 0.0
        self.pitching_addition: float = 0.0
        self.defense_addition: float = 0.0
        self.base_running_addition: float = 0.0
        self.player_additives = self.pre_load_additives()
        self.calc_additives()
        self._calculate_defense()

    def validate_game_state_additives(self, cur_runs: Decimal):
        if self.team_enum in team_game_event_map:
            buff, start_season, end_season, req_weather = team_game_event_map[self.team_enum]
            if buff == GameEventTeamBuff.PRESSURE and \
                    self.season >= start_season and \
                    req_weather == self.weather and \
                    self.runners_aboard:
                self.batting_addition = 0.25
                self.pitching_addition = 0.25
                self.defense_addition = 0.25
                self.base_running_addition = 0.25
            if buff == GameEventTeamBuff.PRESSURE and \
                    self.season >= start_season and \
                    req_weather == self.weather and \
                    not self.runners_aboard:
                self.batting_addition = 0.0
                self.pitching_addition = 0.0
                self.defense_addition = 0.0
                self.base_running_addition = 0.0

        for player_id in self.player_buffs.keys():
            cur_buffs = self.player_buffs[player_id]
            for cur_mod in cur_buffs.keys():
                if cur_mod == PlayerBuff.UNDER_OVER and cur_buffs[cur_mod] == 2 and cur_runs > 5:
                    # turn off the buff
                    self.player_buffs[player_id][cur_mod] = 1
                    self.player_additives[player_id][AdditiveTypes.BATTING] -= 0.2
                    self.player_additives[player_id][AdditiveTypes.PITCHING] -= 0.2
                    self.player_additives[player_id][AdditiveTypes.DEFENSE] -= 0.2
                    self.player_additives[player_id][AdditiveTypes.BASE_RUNNING] -= 0.2
                if cur_mod == PlayerBuff.UNDER_OVER and cur_buffs[cur_mod] == 1 and cur_runs < 5:
                    # turn on the buff
                    self.player_buffs[player_id][cur_mod] = 2
                    self.player_additives[player_id][AdditiveTypes.BATTING] += 0.2
                    self.player_additives[player_id][AdditiveTypes.PITCHING] += 0.2
                    self.player_additives[player_id][AdditiveTypes.DEFENSE] += 0.2
                    self.player_additives[player_id][AdditiveTypes.BASE_RUNNING] += 0.2
                if cur_mod == PlayerBuff.OVER_UNDER and cur_buffs[cur_mod] == 1 and cur_runs > 5:
                    # turn on the debuff
                    self.player_buffs[player_id][cur_mod] = 2
                    self.player_additives[player_id][AdditiveTypes.BATTING] -= 0.2
                    self.player_additives[player_id][AdditiveTypes.PITCHING] -= 0.2
                    self.player_additives[player_id][AdditiveTypes.DEFENSE] -= 0.2
                    self.player_additives[player_id][AdditiveTypes.BASE_RUNNING] -= 0.2
                if cur_mod == PlayerBuff.OVER_UNDER and cur_buffs[cur_mod] == 2 and cur_runs <= 5:
                    # turn off the debuff
                    self.player_buffs[player_id][cur_mod] = 1
                    self.player_additives[player_id][AdditiveTypes.BATTING] += 0.2
                    self.player_additives[player_id][AdditiveTypes.PITCHING] += 0.2
                    self.player_additives[player_id][AdditiveTypes.DEFENSE] += 0.2
                    self.player_additives[player_id][AdditiveTypes.BASE_RUNNING] += 0.2

    def apply_hit_to_buffs(self, player_id: str):
        if PlayerBuff.SPICY in self.player_buffs[player_id]:
            if self.player_buffs[player_id][PlayerBuff.SPICY] < 3:
                self.player_buffs[player_id][PlayerBuff.SPICY] += 1
            else:
                if self.player_buffs[player_id][PlayerBuff.SPICY] == 3:
                    self.player_buffs[player_id][PlayerBuff.SPICY] += 1
                    self.player_additives[player_id][AdditiveTypes.BATTING] += 0.5

    def reset_hit_buffs(self, player_id: str):
        if PlayerBuff.SPICY in self.player_buffs[player_id]:
            if self.player_buffs[player_id][PlayerBuff.SPICY] == 4:
                self.player_additives[player_id][AdditiveTypes.BATTING] -= 0.5
            self.player_buffs[player_id][PlayerBuff.SPICY] = 1

    def pre_load_additives(self) -> Dict[str, Dict[AdditiveTypes, float]]:
        player_additives = {}
        for player_id in self.player_buffs.keys():
            cur_additives = {
                AdditiveTypes.BATTING: 0.0,
                AdditiveTypes.PITCHING: 0.0,
                AdditiveTypes.DEFENSE: 0.0,
                AdditiveTypes.BASE_RUNNING: 0.0,
            }
            for cur_mod in self.player_buffs[player_id].keys():
                if cur_mod == PlayerBuff.CHUNKY and self.weather == Weather.PEANUTS:
                    cur_additives[AdditiveTypes.BATTING] += 1.0
                if cur_mod == PlayerBuff.SMOOTH and self.weather == Weather.PEANUTS:
                    cur_additives[AdditiveTypes.BASE_RUNNING] += 1.0
                if cur_mod == PlayerBuff.UNDER_OVER or \
                        (cur_mod == PlayerBuff.HOMEBODY and self.is_home) or \
                        (cur_mod == PlayerBuff.PERK and
                         self.weather in [Weather.COFFEE, Weather.COFFEE2, Weather.COFFEE3]):
                    # turn on the buff
                    self.player_buffs[player_id][cur_mod] = 2
                    cur_additives[AdditiveTypes.BATTING] += 0.2
                    cur_additives[AdditiveTypes.PITCHING] += 0.2
                    cur_additives[AdditiveTypes.DEFENSE] += 0.2
                    cur_additives[AdditiveTypes.BASE_RUNNING] += 0.2
                if cur_mod == PlayerBuff.HOMEBODY and not self.is_home:
                    self.player_buffs[player_id][cur_mod] = 1
                    cur_additives[AdditiveTypes.BATTING] -= 0.2
                    cur_additives[AdditiveTypes.PITCHING] -= 0.2
                    cur_additives[AdditiveTypes.DEFENSE] -= 0.2
                    cur_additives[AdditiveTypes.BASE_RUNNING] -= 0.2
            player_additives[player_id] = cur_additives
        return player_additives

    def reset_preload_additives(self) -> None:
        self.player_additives = self.pre_load_additives()

    def _calculate_defense(self):
        """Calculate the average team defense and store it in the stlats dict under DEF_ID"""
        anticapitalism: List[float] = []
        chasiness: List[float] = []
        omniscience: List[float] = []
        tenaciousness: List[float] = []
        watchfulness: List[float] = []
        defense_vibes: List[float] = []
        defense_pressurization: List[float] = []
        defense_cinnamon: List[float] = []
        for pos in self.lineup.keys():
            cur_id: str = self.lineup[pos]
            player_def_additive = self.player_additives[cur_id][AdditiveTypes.DEFENSE]
            anticapitalism.append(self.stlats[cur_id][FK.ANTICAPITALISM] + self.defense_addition + player_def_additive)
            chasiness.append(self.stlats[cur_id][FK.CHASINESS] + self.defense_addition + player_def_additive)
            omniscience.append(self.stlats[cur_id][FK.OMNISCIENCE] + self.defense_addition + player_def_additive)
            tenaciousness.append(self.stlats[cur_id][FK.TENACIOUSNESS] + self.defense_addition + player_def_additive)
            watchfulness.append(self.stlats[cur_id][FK.WATCHFULNESS] + self.defense_addition + player_def_additive)
            defense_pressurization.append(self.stlats[cur_id][FK.PRESSURIZATION])
            defense_cinnamon.append(self.stlats[cur_id][FK.CINNAMON])
            defense_vibes.append(calc_vibes(self.stlats[cur_id][FK.PRESSURIZATION],
                                            self.stlats[cur_id][FK.CINNAMON],
                                            self.stlats[cur_id][FK.BUOYANCY],
                                            self.day
                                            ))

        def_anticapitalism = statistics.mean(anticapitalism)
        def_chasiness = statistics.mean(chasiness)
        def_omniscience = statistics.mean(omniscience)
        def_tenaciousness = statistics.mean(tenaciousness)
        def_watchfulness = statistics.mean(watchfulness)
        def_vibes = statistics.mean(defense_vibes)

        self.stlats[DEF_ID]: Dict[FK, float] = {}
        self.stlats[DEF_ID][FK.ANTICAPITALISM] = def_anticapitalism
        self.stlats[DEF_ID][FK.CHASINESS] = def_chasiness
        self.stlats[DEF_ID][FK.OMNISCIENCE] = def_omniscience
        self.stlats[DEF_ID][FK.TENACIOUSNESS] = def_tenaciousness
        self.stlats[DEF_ID][FK.WATCHFULNESS] = def_watchfulness
        self.stlats[DEF_ID][FK.VIBES] = def_vibes

    def reset_team_state(self, game_stat_reset=False, lineup_changed=True) -> None:
        if game_stat_reset:
            self.reset_game_stats()
        self.cur_batter_pos = 1
        self.cur_batter = self.lineup[self.cur_batter_pos]
        if lineup_changed:
            self.player_additives = self.pre_load_additives()
            self.calc_additives()
        self._calculate_defense()

    def reset_game_stats(self) -> None:
        new_dict: Dict[Stats, float] = {}
        for k in Stats:
            new_dict[k] = 0.0
        for p_key in self.lineup.keys():
            self.game_stats[self.lineup[p_key]] = new_dict
        self.game_stats[self.starting_pitcher] = new_dict
        self.game_stats[DEF_ID] = new_dict
        self.game_stats[TEAM_ID] = new_dict

    def update_player_names(self, new_names: Dict[str, str]):
        for id in new_names:
            if id not in self.player_names:
                self.player_names[id] = new_names[id]

    def to_dict(self) -> Dict[str, Any]:
        """ Gets a dict representation of the state for serialization """
        serialization_dict = {
            "team_id": self.team_id,
            "season": self.season,
            "day": self.day,
            "stadium": Stadium.to_dict(self.stadium),
            "weather": self.weather.value,
            "is_home": self.is_home,
            "num_bases": self.num_bases,
            "balls_for_walk": self.balls_for_walk,
            "strikes_for_out": self.strikes_for_out,
            "outs_for_inning": self.outs_for_inning,
            "lineup": self.lineup,
            "rotation": self.rotation,
            "starting_pitcher": self.starting_pitcher,
            "stlats": TeamState.convert_dict(self.stlats),
            "buffs": TeamState.convert_buffs(self.player_buffs),
            "game_stats": TeamState.convert_dict(self.game_stats),
            "segmented_stats": TeamState.convert_segmented_stats(self.segmented_stats),
            "segment_size": self.segment_size,
            "blood": TeamState.convert_blood(self.blood),
            "player_names": self.player_names,
            "cur_batter_pos": self.cur_batter_pos,
        }
        return serialization_dict

    def save(self, storage_path: str) -> None:
        """ Persist a serialized json of the team state """
        with open(storage_path, "w") as json_file:
            json.dump(self.to_dict(), json_file)

    @classmethod
    def load(cls, storage_path: str):
        with open(storage_path, "r") as team_state_file:
            team_state_json = json.load(team_state_file)
            try:
                ret_val = TeamState.from_config(team_state_json)
                return ret_val
            except KeyError:
                logging.warning(
                    "Unable to load team state file: " + storage_path
                )
                return None

    @classmethod
    # TODO(kjc9): Force serialization to account for the new player buffs and additives and segmented stats
    def from_config(cls, team_state: Dict[str, Any]):
        """Reconstructs a team state from a json file."""
        team_id: str = team_state["team_id"]
        season: int = team_state["season"]
        day: int = team_state["day"]
        stadium: Stadium = Stadium.from_config(team_state['stadium'])
        num_bases: int = team_state["num_bases"]
        weather: Weather = Weather(team_state["weather"])
        is_home: bool = team_state["is_home"]
        balls_for_walk: int = team_state["balls_for_walk"]
        strikes_for_out: int = team_state["strikes_for_out"]
        outs_for_inning: int = team_state["outs_for_inning"]
        lineup: Dict[int, str] = TeamState.encode_lineup(team_state["lineup"])
        rotation: Dict[int, str] = TeamState.encode_lineup(team_state["rotation"])
        starting_pitcher: str = team_state["starting_pitcher"]
        stlats: Dict[str, Dict[FK, float]] = TeamState.encode_stlats(team_state["stlats"])
        buffs: Dict[str, Dict[PlayerBuff, int]] = TeamState.encode_buffs(team_state["buffs"])
        game_stats: Dict[str, Dict[Stats, float]] = TeamState.encode_game_stats(team_state["game_stats"])
        segmented_stats: Dict[int, Dict[str, Dict[Stats, float]]] = TeamState.encode_segmented_stats(team_state["segmented_stats"])
        segment_size: int = team_state["segment_size"]
        blood: Dict[str, BloodType] = TeamState.encode_blood(team_state["blood"])
        player_names: Dict[str, str] = team_state["player_names"]
        cur_batter_pos: int = team_state["cur_batter_pos"]
        return cls(
            team_id,
            season,
            day,
            stadium,
            weather,
            is_home,
            num_bases,
            balls_for_walk,
            strikes_for_out,
            outs_for_inning,
            lineup,
            rotation,
            starting_pitcher,
            stlats,
            buffs,
            game_stats,
            segmented_stats,
            blood,
            player_names,
            cur_batter_pos,
            segment_size,
        )

    @classmethod
    def encode_stlats(cls, raw: Dict[str, Dict[int, float]]) -> Dict[str, Dict[FK, float]]:
        ret_val: Dict[str, Dict[FK, float]] = {}
        for key in raw:
            new_dict: Dict[FK, float] = {}
            for stat in raw[key]:
                new_dict[FK(int(stat))] = raw[key][stat]
            ret_val[key] = new_dict
        return ret_val

    @classmethod
    def encode_buffs(cls, raw: Dict[str, Dict[int, int]]) -> Dict[str, Dict[PlayerBuff, int]]:
        ret_val: Dict[str, Dict[PlayerBuff, int]] = {}
        for key in raw:
            new_dict: Dict[PlayerBuff, int] = {}
            for stat in raw[key]:
                new_dict[PlayerBuff(int(stat))] = raw[key][stat]
            ret_val[key] = new_dict
        return ret_val

    @classmethod
    def encode_game_stats(cls, raw: Dict[str, Dict[int, float]]) -> Dict[str, Dict[Stats, float]]:
        ret_val: Dict[str, Dict[Stats, float]] = {}
        for key in raw:
            new_dict: Dict[Stats, float] = {}
            for stat in raw[key]:
                new_dict[Stats(int(stat))] = raw[key][stat]
            ret_val[key] = new_dict
        return ret_val

    @classmethod
    def encode_segmented_stats(cls, raw: Dict[int, Dict[str, Dict[int, float]]]) -> Dict[int, Dict[str, Dict[Stats, float]]]:
        ret_val: Dict[int, Dict[str, Dict[Stats, float]]] = {}
        for segment in raw:
            new_player: Dict[str, Dict[Stats, float]] = {}
            for player_id in raw[segment]:
                new_stat_dict: Dict[Stats, float] = {}
                for stat in raw[segment][player_id]:
                    new_stat_dict[Stats(int(stat))] = raw[segment][player_id][stat]
                new_player[player_id] = new_stat_dict
            ret_val[int(segment)] = new_player
        return ret_val

    @classmethod
    def encode_blood(cls, raw: Dict[str, int]) -> Dict[str, BloodType]:
        ret_val: Dict[str, BloodType] = {}
        for key in raw:
            ret_val[key] = BloodType(int(raw[key]))
        return ret_val

    @classmethod
    def encode_lineup(cls, raw: Dict[str, str]) -> Dict[int, str]:
        ret_val: Dict[int, str] = {}
        for key in raw:
            ret_val[int(key)] = raw[key]
        return ret_val

    @classmethod
    def convert_dict(cls, encoded: Dict[str, Dict[Any, float]]) -> Dict[str, Dict[int, float]]:
        ret_val: Dict[str, Dict[int, float]] = {}
        for key in encoded:
            new_dict: Dict[int, float] = {}
            for stat in encoded[key]:
                new_dict[stat.value] = encoded[key][stat]
            ret_val[key] = new_dict
        return ret_val

    @classmethod
    def convert_buffs(cls, encoded: Dict[str, Dict[Any, int]]) -> Dict[str, Dict[int, int]]:
        ret_val: Dict[str, Dict[int, int]] = {}
        for key in encoded:
            new_dict: Dict[int, int] = {}
            for stat in encoded[key]:
                new_dict[stat.value] = encoded[key][stat]
            ret_val[key] = new_dict
        return ret_val

    @classmethod
    def convert_segmented_stats(
        cls,
        encoded: Dict[int, Dict[str, Dict[Any, float]]]
    ) -> Dict[int, Dict[str, Dict[int, float]]]:
        ret_val: Dict[int, Dict[str, Dict[int, float]]] = {}
        for segment in encoded:
            new_player_dict: Dict[str, Dict[int, float]] = {}
            for player_id in encoded[segment]:
                new_stat_dict: Dict[int, float] = {}
                for stat in encoded[segment][player_id]:
                    new_stat_dict[stat.value] = encoded[segment][player_id][stat]
                new_player_dict[player_id] = new_stat_dict
            ret_val[segment] = new_player_dict
        return ret_val

    @classmethod
    def convert_blood(cls, encoded: Dict[str, BloodType]) -> Dict[str, int]:
        ret_val: Dict[str, int] = {}
        for key in encoded:
            ret_val[key] = encoded[key].value
        return ret_val

    def get_player_stats_by_id(self, player_id: str) -> Dict[str, float]:
        return self.stats[player_id]

    def next_batter(self) -> None:
        if len(self.lineup) == self.cur_batter_pos:
            self.cur_batter_pos = 1
        else:
            self.cur_batter_pos += 1
        self.cur_batter = self.lineup[self.cur_batter_pos]

    def next_pitcher(self) -> int:
        if len(self.rotation) == self.cur_pitcher_pos:
            self.cur_pitcher_pos = 1
        else:
            self.cur_pitcher_pos += 1
        return self.cur_pitcher_pos

    def update_stat(self, player_id: str, stat_id: Stats, value: float, day: int) -> None:
        if player_id not in self.game_stats:
            self.game_stats[player_id] = {}
        if stat_id in self.game_stats[player_id]:
            self.game_stats[player_id][stat_id] += value
        else:
            self.game_stats[player_id][stat_id] = value

        if day not in self.segmented_stats:
            self.segmented_stats[day] = {}
        if player_id not in self.segmented_stats[day]:
            self.segmented_stats[day][player_id] = {}
        if stat_id in self.segmented_stats[day][player_id]:
            self.segmented_stats[day][player_id][stat_id] += value
        else:
            self.segmented_stats[day][player_id][stat_id] = value

    def get_defense_feature_vector(self) -> List[float]:
        ret_val: List[float] = [
            self.stlats[DEF_ID][FK.ANTICAPITALISM],
            self.stlats[DEF_ID][FK.CHASINESS],
            self.stlats[DEF_ID][FK.OMNISCIENCE],
            self.stlats[DEF_ID][FK.TENACIOUSNESS],
            self.stlats[DEF_ID][FK.WATCHFULNESS],
            self.stlats[DEF_ID][FK.VIBES],
        ]
        return ret_val

    def get_pitcher_feature_vector(self) -> List[float]:
        player_id = self.starting_pitcher
        player_pitching_additive = self.player_additives[player_id][AdditiveTypes.PITCHING]
        ret_val: List[float] = [
            self.stlats[player_id][FK.COLDNESS] + self.pitching_addition + player_pitching_additive,
            self.stlats[player_id][FK.OVERPOWERMENT] + self.pitching_addition + player_pitching_additive,
            self.stlats[player_id][FK.RUTHLESSNESS] + self.pitching_addition + player_pitching_additive,
            self.stlats[player_id][FK.SHAKESPEARIANISM] + self.pitching_addition + player_pitching_additive,
            self.stlats[player_id][FK.SUPPRESSION] + self.pitching_addition + player_pitching_additive,
            self.stlats[player_id][FK.UNTHWACKABILITY] + self.pitching_addition + player_pitching_additive,
            calc_vibes(self.stlats[player_id][FK.PRESSURIZATION],
                       self.stlats[player_id][FK.CINNAMON],
                       self.stlats[player_id][FK.BUOYANCY],
                       self.day
                       ),
        ]
        return ret_val

    def get_batter_feature_vector(self, player_id: str) -> List[float]:
        new_path = self.stlats[player_id][FK.PATHETICISM] - self.batting_addition
        if new_path < 0.001:
            new_path = 0.001
        player_batting_additive = self.player_additives[player_id][AdditiveTypes.BATTING]
        player_base_running_additive = self.player_additives[player_id][AdditiveTypes.BASE_RUNNING]
        ret_val: List[float] = [
            self.stlats[player_id][FK.BUOYANCY] + self.batting_addition + player_batting_additive,
            self.stlats[player_id][FK.DIVINITY] + self.batting_addition + player_batting_additive,
            self.stlats[player_id][FK.MARTYRDOM] + self.batting_addition + player_batting_additive,
            self.stlats[player_id][FK.MOXIE] + self.batting_addition + player_batting_additive,
            self.stlats[player_id][FK.MUSCLITUDE] + self.batting_addition + player_batting_additive,
            new_path,
            self.stlats[player_id][FK.THWACKABILITY] + self.batting_addition + player_base_running_additive,
            self.stlats[player_id][FK.TRAGICNESS],
            self.stlats[player_id][FK.BASE_THIRST] + self.base_running_addition + player_base_running_additive,
            self.stlats[player_id][FK.CONTINUATION] + self.base_running_addition + player_base_running_additive,
            self.stlats[player_id][FK.GROUND_FRICTION] + self.base_running_addition + player_base_running_additive,
            self.stlats[player_id][FK.INDULGENCE] + self.base_running_addition + player_base_running_additive,
            self.stlats[player_id][FK.LASERLIKENESS] + self.base_running_addition + player_base_running_additive,
            calc_vibes(self.stlats[player_id][FK.PRESSURIZATION],
                       self.stlats[player_id][FK.CINNAMON],
                       self.stlats[player_id][FK.BUOYANCY],
                       self.day
                       ),
        ]
        return ret_val

    def get_runner_feature_vector(self, player_id: str) -> List[float]:
        ret_val: List[float] = [
            self.stlats[player_id][FK.BASE_THIRST],
            self.stlats[player_id][FK.CONTINUATION],
            self.stlats[player_id][FK.GROUND_FRICTION],
            self.stlats[player_id][FK.INDULGENCE],
            self.stlats[player_id][FK.LASERLIKENESS],
            calc_vibes(self.stlats[player_id][FK.PRESSURIZATION],
                       self.stlats[player_id][FK.CINNAMON],
                       self.stlats[player_id][FK.BUOYANCY],
                       self.day
                       ),
        ]
        return ret_val

    def get_cur_batter_feature_vector(self) -> List[float]:
        return self.get_batter_feature_vector(self.cur_batter)

    def get_player_name(self, player_id: str) -> str:
        if player_id in self.player_names:
            return self.player_names[player_id]
        else:
            return "Unknown Player (" + player_id + ")"

    def get_cur_batter_name(self) -> str:
        return self.get_player_name(self.cur_batter)

    def get_cur_pitcher_name(self) -> str:
        return self.get_player_name(self.starting_pitcher)

    def calc_additives(self):
        self.reset_team_additives()
        if self.team_enum in team_game_event_map:
            buff, start_season, end_season, req_weather = team_game_event_map[self.team_enum]
            if buff == GameEventTeamBuff.CROWS and self.season >= start_season and req_weather == self.weather:
                self.batting_addition = 0.5
                self.pitching_addition = 0.5
            if buff == GameEventTeamBuff.PRESSURE and \
                    self.season >= start_season and \
                    req_weather == self.weather and \
                    self.runners_aboard:
                self.batting_addition = 0.25
                self.pitching_addition = 0.25
                self.defense_addition = 0.25
                self.base_running_addition = 0.25
            if buff == GameEventTeamBuff.TRAVELLING and self.season >= start_season and not self.is_home:
                self.batting_addition = 0.05
                self.pitching_addition = 0.05
                self.defense_addition = 0.05
                self.base_running_addition = 0.05
            if buff == GameEventTeamBuff.SINKING_SHIP and self.season >= start_season:
                total_players = len(self.rotation) + len(self.lineup)
                mod = (14 - total_players) * 0.01
                self.batting_addition = mod
                self.pitching_addition = mod
                self.defense_addition = mod
                self.base_running_addition = mod

    def reset_team_additives(self):
        self.batting_addition = 0.0
        self.pitching_addition = 0.0
        self.base_running_addition = 0.0
        self.defense_addition = 0.0
