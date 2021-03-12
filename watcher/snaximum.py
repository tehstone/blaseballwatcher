"""
Very hasty POC for optimizing snack purchasing.
Two models/strategies are offered:
1. Optimizing your income-per-day ("LONG_TERM"), or
2. Optimizing your ROI as measured at the end of the season ("SEASON").
LONG_TERM relevant values:
 - Δgross: increase in hypothetical income since day0 of this season
 - Δipd: increase in Income Per Day (IPD).
 - ratio: Δipd / cost-of-upgrade.
SEASON relevant values:
 - gross(S): income through end-of-season as a result of this purchase
 - profit(S): gross(S) minus the cost. Negative won't pay for itself this season.
 - ROI(S): Seasonal ROI (profit(S) / cost); Negative won't pay for itself this season.
Caveats:
Data problems:
1. Data comes mostly from Chronicler and Blaseball-Reference. Sometimes these
   sources are gently out of date.
2. Number of players washed away in floods is still manually entered.
3. Startup cost is somewhat high. Not every last player needs to be queried at
   startup.
4. Player lookup (for checking for modifications when computing payouts)
   could likely be done on-demand after an initial bulk-query. Right now,
   if a player is missing in fetch data we assume they don't have any
   interesting modifications. This might not be true.
Model problems:
1. Payout data is normalized per-diem, but clumsily. This undervalues batters
   introduced late in a season.
2. Deceased, Shelled, Elsewhere, etc batters do not have ther per-diem payouts
   set to 0.
3. Payout data is not capable of recognizing abrupt shifts in average; e.g. if a
   batter starts performing massively better or worse. The same holds true for
   Black Hole or Flooded Runners calculations. It is based on the entire season
   only.
4. Early season recommendations are going to be very wrong until the data
   settles out; previous season's data is not consulted.
5. Snacks are optimized per-snack instead of per-snaxfolio. This means that
   if the next best upgrade is something expensive (like a wetzel), the
   algorithm will prefer to "wait" for it, even if you can afford other
   upgrades in the meantime.
   A limited stop-gap against this is the `impatient=True` setting, which
   will attempt to spend ALL of the coins, even with suboptimal purchases.
   However, the model is still per-snack and does not measure a snaxfolio-wide
   ROI, which *may* offer slightly different choices that are better in the
   extremely near-term.
6. Idol switching costs are not modeled. They are presumed negligible so far.
7. Popcorn, Stale Popcorn, Burgers and Chips are not modeled at present.
8. Snake Oil recommendations are based on your estimated "betting consistency",
   i.e. how many games per day you actually bet on. It's only a rough estimate;
   maybe all the lucrative betting games are while you're asleep? Your waking
   and sleeping hours are not modeled.

	# Initializing
#>>> from snax import Snaximum
#>>> snax = Snaximum()
Opening upgrades.json ...OK
Getting player data ...OK
Getting batting statistics ...OK
Getting black hole data ...OK (20)
Getting bet data ...OK
Calculating optimal betting threshold ...0.53
  (Override via `betting_threshold` property if desired.)
Assuming flooded runners count this season is 180
  (Adjust via `flooded_runners` property as needed.)
Assuming your betting consistency is 0.58
  (Adjust via `betting_consistency` as desired. Set to 0.0 for full-passive.)

# Updating flooded runners counts
#>>> snax.runners_flooded = 180
# Setting your betting preferences:
# consistency of 0.00 is pure passive, 1.00 is perfect robot.
# 14/24 should be a reasonable target for hardcore players.
# 6/24 is probably good if you bet only sometimes.
#>>> snax.betting_threshold = 0.51
#>>> snax.betting_consistency = (14/24)
# Viewing leaderboards, assuming maximum snacks owned.  Results show the
# total amount of money that could have been earned by that idol for
# existing play this season.
#>>> snax.lucrative_batters()
277000 (62H, 10HR, 48SB) Goodwin Morin
273000 (62H, 15HR, 40SB) Don Mitchell
268500 (71H, 18HR, 30SB) Aldon Cashmoney
249000 (76H, 21HR, 17SB) Valentine Games
240000 (90H, 15HR, 15SB) Dudley Mueller
239500 (67H, 13HR, 29SB) Comfort Septemberish
208000 (82H, 16HR,  7SB) Jaxon Buckley
202000 (38H,  1HR, 47SB) Richardson Games
199500 (57H, 15HR, 18SB) Conner Haley
199000 (82H, 13HR,  8SB) Baby Doyle
# The same command, but with a specific assortment of snacks:
#>>> snaxfolio = {'dogs': 26, 'seeds': 95, 'pickles': 56, 'slushies': 85,
#                 'wetzels': 24, 'snoil': 64}
#>>> snax.lucrative_batters(snaxfolio)
180664 (62H, 10HR, 48SB) Goodwin Morin
172199 (62H, 15HR, 40SB) Don Mitchell
171097 (71H, 18HR, 30SB) Aldon Cashmoney
169530 (90H, 15HR, 15SB) Dudley Mueller
159172 (76H, 21HR, 17SB) Valentine Games
158509 (67H, 13HR, 29SB) Comfort Septemberish
145509 (82H, 16HR,  7SB) Jaxon Buckley
144109 (82H, 13HR,  8SB) Baby Doyle
135470 (40H,  7HR,  2SB) York Silk
135396 (38H,  1HR, 47SB) Richardson Games
# Getting a proposed snack upgrade schedule. If a snack purchase makes a
# new idol more profitable in retrospect, it will print out a
# recommendation to switch. It will always print this line before the
# first pickle/dog/seed item. It doesn't print out which idol it assumes
# you have, though.
# The "dx" is the increase in the "profit you would have had ..." figure.
# ratio is just dx/cost, showing the relative gain for your troubles.
# This is an empty upgrade schedule, cut off after ten items:
# (The value returned is a new snaxfolio with updated counts.)
#>>> snax.propose_upgrades(cash=50000)
01: Buy snoil    for    0 (dx: 1283; ratio: inf)
--- Switch idol to Goodwin Morin
02: Buy pickles  for   10 (dx: 2400; ratio: 240.000)
03: Buy slushies for   10 (dx: 1800; ratio: 180.000)
04: Buy slushies for   10 (dx:  900; ratio: 90.000)
05: Buy pickles  for   20 (dx: 1440; ratio: 72.000)
06: Buy snoil    for   20 (dx: 1292; ratio: 64.600)
07: Buy slushies for   15 (dx:  900; ratio: 60.000)
08: Buy slushies for   20 (dx:  900; ratio: 45.000)
09: Buy pickles  for   35 (dx: 1440; ratio: 41.143)
10: Buy snoil    for   40 (dx: 1283; ratio: 32.075)
...
{'dogs': 9, 'seeds': 15, 'pickles': 26, 'wetzels': 10,
 'slushies': 41, 'popcorn': 0, 'stalecorn': 0, 'snoil': 22,
 'chips': 0, 'burgers': 0}
# Proposed snack schedule upgrade for a specific array of snacks.
# Note that the suggestion doesn't know who you are idoling, so the first snack
# purchase that depends on an idol will note which idol provides that value.
# (The value returned is a new snaxfolio with updated counts.)
#>>> snaxfolio = {'dogs': 26, 'seeds': 95, 'pickles': 51,
                 'slushies': 65, 'wetzels': 15}
#>>> snax.propose_upgrades(cash=50000, snaxfolio=snaxfolio)
01: Buy wetzels  for 7475 (dx: 2945; ratio: 0.394)
02: Buy slushies for 2390 (dx:  900; ratio: 0.377)
--- Switch idol to Goodwin Morin
03: Buy pickles  for 3895 (dx: 1440; ratio: 0.370)
04: Buy slushies for 2435 (dx:  900; ratio: 0.370)
05: Buy wetzels  for 7845 (dx: 2850; ratio: 0.363)
06: Buy slushies for 2480 (dx:  900; ratio: 0.363)
07: Buy pickles  for 4000 (dx: 1440; ratio: 0.360)
08: Buy wetzels  for 8220 (dx: 2945; ratio: 0.358)
09: Buy slushies for 2525 (dx:  900; ratio: 0.356)
10: Buy pickles  for 4105 (dx: 1440; ratio: 0.351)
11: Buy slushies for 2575 (dx:  900; ratio: 0.350)
{'dogs': 26, 'seeds': 95, 'pickles': 59, 'slushies': 90, 'wetzels': 27,
 'snoil': 64, 'popcorn': 0, 'stalecorn': 0, 'chips': 0, 'burgers': 0}
# Upgrades won't overflow beyond their maximum:
#>>> snax.propose_upgrades(cash=50000, snaxfolio=snax.mksnax(maximum=True))
--- No further upgrades available ---
{'dogs': 99, 'seeds': 99, 'pickles': 99, 'wetzels': 99, 'slushies': 99,
 'popcorn': 99, 'stalecorn': 99, 'snoil': 99, 'chips': 99, 'burgers': 99}
Hint: try setting your betting consistency to 0.00 for your
last suggestion of the night before you sleep.
"""
import math
import os

import requests
import json
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Tuple, cast
from blaseball_mike import chronicler, reference
from watcher.bets import Bets

# Aliases for SIBR structures
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


class Strategy(Enum):
    LONG_TERM = 1
    SEASONAL = 2


class Snaximum:
    def __init__(self, bot, season: int) -> None:
        self.bot = bot
        self.current_season = season
        self.betting_threshold = 0.51
        # 0.66: 16/24 bets per day, missing 8 for sleep
        # 0.58: 14/24 bets per day, missing 10
        # 0.50: 12/24 bets per day (You got half!)
        # 0.25: 06/24 bets per day (Got most in the evenings.)
        # 0.00: 00/24 bpd (All passive, all the time, baby!)
        self.betting_consistency = 14 / 24
        self.interactive = True

        self.flooded_runners = 180
        self.black_holes: int = 15
        self.current_day = 60

        # Internal stuff:
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
        #  i.e. (seeds, dogs, pickles) => List[BatterAnalysis]
        self.batter_analysis_cache: Dict[Tuple[int, int, int],
                                         List[BatterAnalysis]] = {}
        self._initialize()

    @property
    def days_remaining(self) -> float:
        return 99 - self.current_day

    def _initialize(self) -> None:
        self.bot.logger.info("Opening upgrades.json ...")
        with open(os.path.join('data', "upgrades.json"), "r") as infile:
            self.upgrades = json.load(infile)
        self.refresh()

    def set_blackhole_count(self, count):
        self.black_holes = count

    def set_flood_count(self, count):
        self.flooded_runners = count

    def set_current_day(self, day):
        self.current_day = day

    def set_current_season(self, season):
        self.current_season = season

    def refresh(self):
        rsp = requests.get("https://www.blaseball.com/database/simulationData")
        assert rsp.status_code == 200
        simulationData = rsp.json()
        self.current_day = simulationData["day"]
        self.current_season = simulationData["season"] + 1

        self.refresh_batting_statistics()
        self.bets = Bets(self.bot, self.current_season, self.interactive)
        if not self.betting_threshold:
            self.refresh_betting_threshold()
        self.refresh_players()
        self.refresh_data()

    def refresh_players(self) -> None:
        self.bot.logger.info("Getting player data ...")
        rsp = requests.get('https://api.blaseball-reference.com/v2/players?season=current')
        assert rsp.status_code == 200
        players = rsp.json()

        rsp = requests.get(f'https://www.blaseball.com/database/games?season='
                           f'{self.current_season-1}&day={self.current_day}')
        assert rsp.status_code == 200
        games = rsp.json()
        team_ids = []
        for game in games:
            team_ids.append(game['homeTeam'])
            team_ids.append(game['awayTeam'])

        for player in players:
            if len(games) > 0:
                if player['team_id'] in team_ids:
                    self.player_map[player['player_id']] = player
            else:
                self.player_map[player['player_id']] = player

    def refresh_batting_statistics(self) -> None:
        if self.interactive:
            print("Getting batting statistics ...", end='')
        data = reference.get_stats(
            type_='season', group='hitting',
            fields=('hits', 'home_runs', 'stolen_bases', 'appearances'),
            season='current'
        )
        assert len(data) == 1
        self.data = data[0]
        self.batter_analysis_cache = {}
        self._reference_days = max(split['stat']['appearances']
                                   for split in self.data['splits'])
        if self.interactive:
            print(f" OK ({len(self.data['splits'])} batters,"
                  f" {self._reference_days} games)")
            print(f"Current Season: {self.current_season}")

    def refresh_betting_threshold(self) -> None:
        if self.interactive:
            print("Calculating optimal betting threshold ...", end='')
        self.betting_threshold = self.bets.calculate_threshold()
        if self.interactive:
            print(" {:0.2f}".format(self.betting_threshold))
            print("  (Override via `betting_threshold` property if desired.)")

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
            'hits': modifier * hit_payout * (stats['hits'] - stats['home_runs']),
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

    def get_lucrative_batters(self, snaxfolio: Optional[Snaxfolio] = None,
                              limit: int = 10) -> List[BatterAnalysis]:
        snaxfolio = self.mksnax(snaxfolio, maximum=True)

        key = (snaxfolio['seeds'], snaxfolio['hot_dog'], snaxfolio['pickles'])

        if key in self.batter_analysis_cache:
            return self.batter_analysis_cache[key][0:limit]

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
        self.batter_analysis_cache[key] = batters

        return batters[0:limit]

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

    def what_if(self, snaxfolio: Snaxfolio,
                which: str) -> Optional[PurchaseAnalysis]:
        """
            Compute profitability analysis on what would have happened if you had
            one more of the named snack (which) at the beginning of this season.
            Returns a dict with these fields:
            - 'which': which snack was purchased; as passed in.
            - 'dx': How much extra profit would have been made this season
            - 'cost': How much the snack costs you right now.
            - 'ratio': dx/cost. Higher is better.
            - 'snaxfolio': A new Snaxfolio with one item incremented.
            - 'idol': Which idol this assessment is based on. It may be None,
                      indicating it doesn't factor into the assessment.
            Note: the 'dx' and therefore also the 'ratio' will be penalized for
                  snake-oil analyses based on the specified betting_consistency.
            May return None; when the specified snack cannot be upgraded.
            """
        snaxfolio = self.mksnax(snaxfolio)

        if self.upgrades_left(which, snaxfolio[which]) <= 0:
            return None

        # Idol-related items will set this as needed.
        idol = None

        if which == 'wet_pretzel':
            current_gross = self.black_holes * self.get_payout('wet_pretzel', snaxfolio[which])
            new_gross = self.black_holes * self.get_payout('wet_pretzel', snaxfolio[which] + 1)
            days_seen = self.current_day
        elif which == 'slushies':
            current_gross = self.flooded_runners * self.get_payout('slushies', snaxfolio[which])
            new_gross = self.flooded_runners * self.get_payout('slushies', snaxfolio[which] + 1)
            days_seen = self.current_day
        elif which == 'snake_oil':
            current_gross = self.bets.payout(
                bet=self.get_payout('snake_oil', snaxfolio[which]),
                threshold=self.betting_threshold,
                efficiency=self.betting_consistency
            )
            new_gross = self.bets.payout(
                bet=self.get_payout('snake_oil', snaxfolio[which] + 1),
                threshold=self.betting_threshold,
                efficiency=self.betting_consistency
            )
            days_seen = self.current_day
        else:  # Battersnax analysis (Not to be confused with Battered Snacks.)
            # Current analysis
            reference = self.get_lucrative_batters(snaxfolio)[0]
            # Hypothetical Analysis
            snaxfolio[which] += 1
            best = self.get_lucrative_batters(snaxfolio)[0]
            snaxfolio[which] -= 1  # Put it back, we'll get it below.
            current_gross = reference[0]['total']
            new_gross = best[0]['total']
            days_seen = self._reference_days
            idol = best[1]['player']

        # Theoretical increase in gross income from day0 until now:
        delta_gross = new_gross - current_gross

        # Delta Income-Per-Day: change in estimated income per game-day.
        dipd = delta_gross / days_seen

        # How much does it cost to upgrade this snack?
        cost = self.get_cost(which, snaxfolio[which])

        # Increase in income-per-day, per-coin spent. This is a long-term strategy.
        ratio = (dipd / cost) if cost else math.inf
        # The seasonal gross income is the delta income-per-day * days_left
        seasonal_gross_income = (99 - days_seen) * dipd
        # Seasonal profit is simply the seasonal_gross_income - cost.
        seasonal_profit = seasonal_gross_income - cost
        # Seasonal ROI is (seasonal_profit / cost).
        seasonal_roi = (seasonal_profit / cost) if cost else math.inf
        # Increment the snaxfolio and return
        snaxfolio[which] += 1

        return {
            'which': which,  # Which item is this analysis for?
            'cost': cost,
            'idol': idol,  # Under which idol are these figures calculated?
            'snaxfolio': snaxfolio,  # (Adjusted for new assortment.)
            'Δgross': delta_gross,
            'Δipd': dipd, # new dx?
            'ratio': ratio,  # Delta-Income-Per-Day / Cost
            'sgi': seasonal_gross_income,
            'sprofit': seasonal_profit,
            'sroi': seasonal_roi,
        }

    def calc_upgrade_costs(self, snaxfolio: Optional[Snaxfolio],
                           ignore_list: Optional[list],
                           strategy: Strategy = Strategy.LONG_TERM
                           ) -> List[PurchaseAnalysis]:
        if ignore_list is None:
            ignore_list = []
        snaxfolio = self.mksnax(snaxfolio)

        choice_list = ['pickles', 'seeds', 'hot_dog', 'wet_pretzel', 'slushies', 'snake_oil']
        choices = [self.what_if(snaxfolio, item) for item in choice_list if item not in ignore_list]

        if strategy == Strategy.LONG_TERM:
            sort_key = 'ratio'
        else:
            sort_key = 'sroi'

        return sorted(
            # mypy can't infer that filter(None, ...) sheds Optional[T]
            cast(Iterable[PurchaseAnalysis], filter(None, choices)),
            key=lambda x: cast(float, x[sort_key]),
            reverse=True
        )

    def propose_upgrade(self, snaxfolio: Optional[Snaxfolio],
                        strategy: Strategy = Strategy.LONG_TERM) -> None:
        snaxfolio = self.mksnax(snaxfolio)
        proposals = self.calc_upgrade_costs(snaxfolio, strategy)
        if not proposals:
            print("--- No further upgrades available ---")
            return
        for proposal in proposals:
            print("{:8s}: cost {:4d}; Δgross: {:4d}; Δipd: {:5.2f}; ratio: {:4.2f}; ".format(
                proposal['which'],
                proposal['cost'],
                proposal['Δgross'],
                proposal['Δipd'],
                proposal['ratio']
            ), end='')
            print("gross(S): {:7.2f}; profit(S): {:7.2f}; ROI(S): {:5.2f}".format(
                proposal['sgi'],
                proposal['sprofit'],
                proposal['sroi'],
            ))

    def do_propose_upgrades(self, coins: int = 250,
                            snaxfolio: Optional[Snaxfolio] = None,
                            ignore_list=None,
                            strategy: Strategy = Strategy.LONG_TERM,
                            impatient: bool = False):
        snaxfolio = self.mksnax(snaxfolio)
        schedule: List[Optional[PurchaseAnalysis]] = []

        spent = 0
        proposal_dict = {"change_idol": False, "buy_list": schedule, "none_available": False}
        while True:
            proposals = self.calc_upgrade_costs(snaxfolio, ignore_list, strategy)
            if not proposals:
                schedule.append(None)
                proposal_dict["none_available"] = True
                break
            proposal = None
            if not impatient:
                proposal = proposals[0]
            else:
                for proposal in proposals:
                    if spent + proposal['cost'] <= coins:
                        # We can afford this one!
                        break
            if not proposal:
                break
            if proposal != proposals[0]:
                # This choice is not necessarily optimal
                proposal['impatient'] = True
            spent += proposal['cost']
            if spent > coins:
                break

            schedule.append(proposal)
            snaxfolio = proposal['snaxfolio']
        return proposal_dict
