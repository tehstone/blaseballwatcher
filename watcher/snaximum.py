"""
Very hasty POC for tracking snack/idol synergy.


Caveats:

Data problems:
1. It doesn't use any of the nice packages to get stats, oops
2. The startup cost is outrageous and it could stand to be properly cached
3. Player lookup could stand to be on-demand after initial bulk query
4. Black holes is just manually set, I didn't know where to query it.
5. Ditto for number of players washed away in floods.

Model problems:
6. Optimizations are based around maximizing theoretical profit in the
   season-so-far. This works out fairly well up to day 49, but not beyond.
7. Snacks are optimized per-purchase instead of per-purchasing-session,
   which leads to some minor inefficiencies (wetzels are favored over slushies)
9. Idol switching costs are not really accounted for in any way.
9. Popcorn, Stale Popcorn, Burgers, Chips, and Snake Oil are not really
   accounted for in any way at all yet.
10. Inventory management is also not really accounted for!


# Initializing

# >>> from snax import Snaximum
# >>> snax = Snaximum()
Getting player data ...
OK
Getting batting statistics ...
OK
Opening upgrades.json ...
OK


# Setting black hole and flooded runners counts
#
# >>> snax.black_holes = 13
# >>> snax.runners_flooded = 92


# Viewing leaderboards, assuming maximum snacks owned.  Results show the
# total amount of money that could have been earned by that idol for
# existing play this season.

# >>> snax.lucrative_batters()
174000 (38H,  6HR, 31SB) Goodwin Morin
156000 (36H,  9HR, 22SB) Don Mitchell
143500 (43H, 13HR,  9SB) Valentine Games
139000 (36H, 10HR, 15SB) Conner Haley
137000 (52H,  8HR,  9SB) Dudley Mueller
135000 (38H,  9HR, 14SB) Aldon Cashmoney
134500 (35H,  7HR, 18SB) Comfort Septemberish
132000 (24H,  6HR,  2SB) York Silk
127000 (32H,  4HR, 21SB) Logan Horseman
126500 (45H, 11HR,  5SB) Jaxon Buckley


# The same command, but with a specific assortment of snacks:

# >>> snaxfolio = {'dogs': 26, 'seeds': 95, 'pickles': 51,
#                  'slushies': 65, 'wetzels': 15}
# >>> snax.lucrative_batters(snaxfolio)
108641 (38H,  6HR, 31SB) Goodwin Morin
 96479 (52H,  8HR,  9SB) Dudley Mueller
 94897 (36H,  9HR, 22SB) Don Mitchell
 88811 (43H, 13HR,  9SB) Valentine Games
 87136 (24H,  6HR,  2SB) York Silk
 85311 (38H,  9HR, 14SB) Aldon Cashmoney
 85180 (35H,  7HR, 18SB) Comfort Septemberish
 85047 (36H, 10HR, 15SB) Conner Haley
 83375 (45H, 11HR,  5SB) Jaxon Buckley
 82459 (32H,  4HR, 21SB) Logan Horseman


# Getting a proposed snack upgrade schedule. If a snack purchase makes a
# new idol more profitable in retrospect, it will print out a
# recommendation to switch. It will always print this line before the
# first pickle/dog/seed item. It doesn't print out which idol it assumes
# you have, though.

# The "dx" is the increase in the "profit you would have had ..." figure.
# ratio is just dx/cost, showing the relative gain for your troubles.

# This is an empty upgrade schedule, cut off after ten items:

# >>> snax.propose_upgrades(cash=50000)
--- Switch idol to Goodwin Morin
01: Buy pickles for    10 (dx:  1550; ratio: 155.0)
02: Buy slushies for    10 (dx:   920; ratio: 92.0)
03: Buy pickles for    20 (dx:   930; ratio: 46.5)
04: Buy slushies for    10 (dx:   460; ratio: 46.0)
05: Buy slushies for    15 (dx:   460; ratio: 30.666666666666668)
06: Buy pickles for    35 (dx:   930; ratio: 26.571428571428573)
07: Buy slushies for    20 (dx:   460; ratio: 23.0)
08: Buy pickles for    60 (dx:   930; ratio: 15.5)
09: Buy slushies for    30 (dx:   460; ratio: 15.333333333333334)
10: Buy slushies for    35 (dx:   460; ratio: 13.142857142857142)


# Proposed snack schedule upgrade for a specific array of snacks.
# (The value returned is a new snaxfolio with updated counts.)

# >>> snaxfolio = {'dogs': 26, 'seeds': 95, 'pickles': 51,
#                  'slushies': 65, 'wetzels': 15}
# >>> snax.propose_upgrades(cash=50000, snaxfolio=snaxfolio)
01: Buy wetzels for  4295 (dx:  1950; ratio: 0.4540162980209546)
02: Buy wetzels for  4635 (dx:  2015; ratio: 0.43473570658036675)
03: Buy wetzels for  4975 (dx:  1950; ratio: 0.39195979899497485)
04: Buy wetzels for  5320 (dx:  1950; ratio: 0.36654135338345867)
05: Buy wetzels for  5670 (dx:  2015; ratio: 0.35537918871252205)
06: Buy wetzels for  6025 (dx:  1950; ratio: 0.3236514522821577)
07: Buy wetzels for  6385 (dx:  2015; ratio: 0.3155833985904464)
08: Buy slushies for  1560 (dx:   460; ratio: 0.2948717948717949)
09: Buy wetzels for  6745 (dx:  1950; ratio: 0.28910303928836173)
10: Buy slushies for  1600 (dx:   460; ratio: 0.2875)
11: Buy slushies for  1635 (dx:   460; ratio: 0.28134556574923547)
{'dogs': 26, 'seeds': 95, 'pickles': 51, 'slushies': 68,
 'wetzels': 23, 'popcorn': 0, 'stalecorn': 0,
 'snoil': 0, 'chips': 0, 'burgers': 0}


# Upgrades won't overflow beyond their maximum:

# >>> snax.propose_upgrades(cash=50000, snaxfolio=snax.mksnax(None, maximum=True))
--- No further upgrades available ---
{'dogs': 99, 'seeds': 99, 'pickles': 99, 'wetzels': 99, 'slushies': 99,
 'popcorn': 99, 'stalecorn': 99, 'snoil': 99, 'chips': 99, 'burgers': 99}

"""
import math
import os

import requests
import json
from typing import Dict, List
from blaseball_mike import reference

from watcher.bets import Bets
from typing import Any, Dict, Iterable, List, Optional, Tuple, cast

# Aliases for SIBR structures
Game = Dict[str, Any]  # Chronicler game data object
Player = Dict[str, Any]  # Reference player data object
StatGroup = Dict[str, Any]  # Reference stats group (group/type/totalSplits/splits)
StatSplit = Dict[str, Any]  # Reference stats split; e.g. StatGroup['splits'][0]
PlayerStats = Dict[str, Any]  # Reference player stats object; e.g. StatSplit['stat']

# Aliases for Blaseball structures
ItemTier = Dict[str, int]  # contains 'price' and 'amount' values
UpgradeData = Dict[str, List[ItemTier]]  # e.g. blackHoleTiers -> List[ItemTier]

# Mapping of snacks to number owned.
Snaxfolio = Dict[str, int]
# Analysis of a Batter's payouts; ('hits', 'home_runs', 'stolen_bases', 'total')
BatterPayout = Dict[str, int]
# Full analysis of a payout.
BatterAnalysis = Tuple[BatterPayout, StatSplit, Player]
# Upgrade analysis dict (cost, dx, ratio, etc.)
PurchaseAnalysis = Dict[str, Any]


class Snaximum:
    def __init__(self) -> None:
        self.betting_threshold = 0.51
        # 0.66: 16/24 bets per day, missing 8 for sleep
        # 0.58: 14/24 bets per day, missing 10
        # 0.50: 12/24 bets per day (You got half!)
        # 0.25: 06/24 bets per day (Got most in the evenings.)
        # 0.00: 00/24 bpd (All passive, all the time, baby!)
        self.betting_consistency = 14 / 24

        self.flooded_runners = 180
        self.black_holes: int = 15
        self.current_day = 60

        # Internal stuff:
        self.bets: Bets
        self.data: StatGroup

        self.player_map: Dict[str, Player] = {}
        self.upgrades: UpgradeData

        self.upgrade_map = {
            'hot_dog': 'idolHomersTiers',
            'seeds': 'idolHitsTiers',
            'pickles': 'idolStealTiers',
            'wet_pretzel': 'blackHoleTiers',
            'slushies': 'floodClearTiers',
            'popcorn': 'teamWinCoinTiers',
            'stalecorn': 'teamLossCoinTiers',
            'snake_oil': 'maxBetTiers',
            'chips': 'idolStrikeoutsTiers',
            'burgers': 'idolShutoutsTiers',
        }
        self._initialize()

    def _initialize(self) -> None:
        print("Opening upgrades.json ...", end='')
        with open(os.path.join('data', "upgrades.json"), "r") as infile:
            self.upgrades = json.load(infile)
        print("OK")
        self.refresh_players()
        self.refresh_data()
        print("Getting bet data ...", end='')
        self.bets = Bets()
        print("OK")
        print("Calculating optimal betting threshold ...", end='')
        self.betting_threshold = self.bets.calculate_threshold()

    def set_blackhole_count(self, count):
        self.black_holes = count

    def set_flood_count(self, count):
        self.flooded_runners = count

    def set_current_day(self, day):
        self.current_day = day

    def refresh_all(self):
        self.refresh_players()
        self.refresh_data()

    def refresh_players(self) -> None:
        print("Getting player data ...", end='')
        rsp = requests.get('https://api.blaseball-reference.com/v2/players?season=current')
        assert rsp.status_code == 200
        print("OK")
        players = rsp.json()
        for player in players:
            self.player_map[player['player_id']] = player

    def refresh_data(self) -> None:
        print("Getting batting statistics ...", end='')
        data = reference.get_stats(
            type_='season', group='hitting',
            fields=('hits', 'home_runs', 'stolen_bases'),
            season='current'
        )
        assert len(data) == 1
        self.data = data[0]
        print("OK")

    def _get_tiers(self, item_name: str) -> List[Dict[str, int]]:
        return self.upgrades[self.upgrade_map[item_name]]

    def get_payout(self, item_name: str, owned: int) -> int:
        if not owned:
            return 0
        return self._get_tiers(item_name)[owned - 1]['amount']

    def get_cost(self, item_name: str, owned: int) -> int:
        tiers = self._get_tiers(item_name)
        return tiers[owned]['price']

    def upgrades_left(self, item_name: str, owned: int) -> int:
        tiers = self._get_tiers(item_name)
        return len(tiers) - owned

    @classmethod
    def payout_modifier(cls, player: Player) -> int:
        mods = player.get('modifications', [])

        if 'CREDIT_TO_THE_TEAM' in mods:
            return 5
        if 'DOUBLE_PAYOUTS' in mods:
            return 2

        return 1

    def calculate_payouts(self, stats: PlayerStats, player: Player, seeds: int,
                          dogs: int, pickles: int) -> BatterPayout:
        hit_payout = self.get_payout('seeds', seeds)
        hr_payout = self.get_payout('hot_dog', dogs)
        sb_payout = self.get_payout('pickles', pickles)

        modifier = self.payout_modifier(player)
        payout = {
            'hits': modifier * hit_payout * stats['hits'],
            'home_runs': modifier * hr_payout * stats['home_runs'],
            'stolen_bases': modifier * sb_payout * stats['stolen_bases'],
        }
        payout['total'] = sum(payout.values())
        return payout

    def mksnax(self, snaxfolio: Optional[Snaxfolio] = None,
               maximum: bool = False) -> Snaxfolio:
        snax: Dict[str, int]
        if not snaxfolio:
            snax = {}
        else:
            snax = snaxfolio.copy()
        for item_name, tier_name in self.upgrade_map.items():
            tier_name = self.upgrade_map[item_name]
            snax.setdefault(
                item_name, len(self.upgrades[tier_name]) if maximum else 0
            )
        return snax

    def get_lucrative_batters(self, snaxfolio: Optional[Snaxfolio] = None
                              ) -> List[BatterAnalysis]:
        snaxfolio = self.mksnax(snaxfolio, maximum=True)

        batters = []
        for split in self.data['splits']:
            stats = cast(PlayerStats, split['stat'])
            player = self.player_map.get(split['player']['id'], {})
            payout = self.calculate_payouts(
                stats, player,
                snaxfolio['seeds'],
                snaxfolio['hot_dog'],
                snaxfolio['pickles']
            )
            batters.append((payout, split, player))

        batters = sorted(batters, key=lambda x: x[0]['total'], reverse=True)
        return batters

    def lucrative_batters(self, snaxfolio: Optional[Snaxfolio] = None) -> None:
        snaxfolio = self.mksnax(snaxfolio, maximum=True)
        batters = self.get_lucrative_batters(snaxfolio)
        for x in batters[0:10]:
            print("{:6d} ({:2d}H, {:2d}HR, {:2d}SB) {:20s}".format(
                x[0]['total'],
                x[1]['stat']['hits'],
                x[1]['stat']['home_runs'],
                x[1]['stat']['stolen_bases'],
                x[1]['player']['fullName'],
            ))

    def what_if(self, reference: BatterAnalysis, snaxfolio: Snaxfolio,
                which: str) -> Optional[PurchaseAnalysis]:
        snaxfolio = self.mksnax(snaxfolio)

        if self.upgrades_left(which, snaxfolio[which]) <= 0:
            return None

        # Copy the current portfolio of snacks owned, increment one of them.
        data = snaxfolio.copy()
        data[which] += 1

        if which == 'wet_pretzel':
            current_value = self.black_holes * self.get_payout('wet_pretzel', snaxfolio[which])
            new_value = self.black_holes * self.get_payout('wet_pretzel', data[which])
            black_holes_per_day = self.black_holes / self.current_day
            remaining = (98 - self.current_day) * black_holes_per_day
            current_value = remaining * self.get_payout('wet_pretzel', snaxfolio[which])
            new_value = remaining * self.get_payout('wet_pretzel', data[which])
            dx = new_value - current_value
            idol = None
        elif which == 'slushies':
            current_value = self.flooded_runners * self.get_payout('slushies', snaxfolio[which])
            new_value = self.flooded_runners * self.get_payout('slushies', data[which])
            floods_per_day = self.flooded_runners / self.current_day
            remaining = (98 - self.current_day) * floods_per_day
            current_value = remaining * self.get_payout('slushies', snaxfolio[which])
            new_value = remaining * self.get_payout('slushies', data[which])
            dx = new_value - current_value
            idol = None
        elif which == 'snake_oil':
            current_value = self.bets.payout(
                bet=self.get_payout('snake_oil', snaxfolio[which]),
                threshold=self.betting_threshold
            )
            new_value = self.bets.payout(
                bet=self.get_payout('snake_oil', data[which]),
                threshold=self.betting_threshold
            )
            current_value = (current_value / self.current_day) * (98 - self.current_day)
            new_value = (new_value / self.current_day) * (98 - self.current_day)
            # Human tax!
            dx = round(self.betting_consistency * (new_value - current_value))
            idol = None
        else:
            # Which idol performs the best under this hypothetical new portfolio?
            best = self.get_lucrative_batters(data)[0]
            # What's the difference over the reference best payout?
            best_remaining = (best[0]['total'] / self.current_day) * (98 - self.current_day)
            ref_remaining = (reference[0]['total'] / self.current_day) * (98 - self.current_day)
            dx = best_remaining - ref_remaining
            #dx = best[0]['total'] - reference[0]['total']
            idol = best[1]['player']['fullName']

        # How much does it cost to upgrade this snack?
        cost = self.get_cost(which, snaxfolio[which])

        # What's the ratio of payout difference to cost? (Higher is better)
        ratio = (dx / cost) if cost else math.inf

        return {
            'which': which,
            'dx': int(dx),
            'cost': cost,
            'ratio': ratio,
            'snaxfolio': data,
            'idol': idol,
        }

    def calc_upgrade_costs(self, snaxfolio: Optional[Snaxfolio], ignore_list: Optional[list], order_by: str
                           ) -> List[PurchaseAnalysis]:
        if ignore_list is None:
            ignore_list = []
        snaxfolio = self.mksnax(snaxfolio)
        best = self.get_lucrative_batters(snaxfolio)[0]

        choice_list = ['pickles', 'seeds', 'hot_dog', 'wet_pretzel', 'slushies', 'snake_oil']
        choices = []
        for item in choice_list:
            if item not in ignore_list:
                choices.append(self.what_if(best, snaxfolio, item))

        return sorted(
            # mypy can't infer that filter(None, ...) sheds Optional[T]
            cast(Iterable[PurchaseAnalysis], filter(None, choices)),
            key=lambda x: cast(float, x[order_by]),
            reverse=True
        )

    def propose_upgrade(self, snaxfolio):
        snaxfolio = self.mksnax(snaxfolio)
        choices = self.calc_upgrade_costs(snaxfolio)
        for choice in choices:
            return "{:8s}: cost {:4d}; dx: {:4d}; ratio: {:0.3f}".format(
                choice['which'],
                choice['cost'],
                choice['dx'],
                choice['ratio'],
            )

    def propose_upgrades(self, cash: int = 10, snaxfolio=None, ignore_list=None, order_by=None) -> Dict:
        snaxfolio = self.mksnax(snaxfolio)

        idol = None
        i = 0
        spent = 0
        proposal_str = ""
        proposal_dict = {"change_idol": False, "buy_list": [], "none_available": False}
        while True:
            i += 1
            proposals = self.calc_upgrade_costs(snaxfolio, ignore_list, order_by)
            if not proposals:
                proposal_dict["none_available"] = True
                break
            proposal = proposals[0]
            spent += proposal['cost']
            if spent > cash:
                break
            if proposal['idol'] is not None:
                if idol != proposal['idol']:
                    proposal_dict["change_idol"] = True
                    idol = proposal['idol']
            snaxfolio = proposal['snaxfolio']
            proposal_dict["buy_list"].append(proposal)
            proposal_str += "\n{:02d}: Buy {:8s} for {:4d} (dx: {:4d}; ratio: {:0.3f})".format(
                i,
                proposal['which'],
                proposal['cost'],
                proposal['dx'],
                proposal['ratio']
            )
        return proposal_dict
