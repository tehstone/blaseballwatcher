import sqlite3


def initialize(db):
    with sqlite3.connect(db) as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS hitterstatstable (
                                                id INTEGER NOT NULL PRIMARY KEY, 
                                                player_id TEXT NOT NULL,
                                                day INTEGER NOT NULL, 
                                                hits INTEGER NOT NULL, 
                                                home_runs INTEGER NOT NULL,
                                                stolen_bases INTEGER NOT NULL);""")
        c.execute("""CREATE TABLE IF NOT EXISTS rulesblogtable (
                                                id INTEGER NOT NULL PRIMARY KEY,
                                                pull_date DATETIME NOT NULL,
                                                page_text TEXT NOT NULL);""")
        c.execute("""CREATE TABLE IF NOT EXISTS usersnaxignoretable (
                                                id INTEGER NOT NULL PRIMARY KEY, 
                                                user_id INTEGER NOT NULL UNIQUE, 
                                                ignore_list TEXT);""")
        c.execute("""CREATE TABLE IF NOT EXISTS usersnaxtable (
                                                id    INTEGER NOT NULL,
                                                user_id   INTEGER NOT NULL UNIQUE,
                                                snake_oil INTEGER DEFAULT 0,
                                                fresh_popcorn INTEGER DEFAULT 0,
                                                stale_popcorn INTEGER DEFAULT 0,
                                                chips INTEGER DEFAULT 0,
                                                burger    INTEGER DEFAULT 0,
                                                hot_dog   INTEGER DEFAULT 0,
                                                seeds INTEGER DEFAULT 0,
                                                pickles   INTEGER DEFAULT 0,
                                                slushies  INTEGER DEFAULT 0,
                                                wet_pretzel   INTEGER DEFAULT 0,
                                                doughnut	INTEGER DEFAULT 0,
                                                sundae	INTEGER DEFAULT 0,
                                                breakfast	INTEGER DEFAULT 0,
                                                lemonade	INTEGER DEFAULT 0,
                                                taffy	INTEGER DEFAULT 0,
                                                meatball	INTEGER DEFAULT 0,
                                                PRIMARY KEY(id)
                                            );""")
        c.execute("""CREATE TABLE IF NOT EXISTS DailyStatSheets (
                                id	TEXT NOT NULL UNIQUE,
                                season	INT NOT NULL,
                                day	INT NOT NULL,
                                playerId	TEXT NOT NULL,
                                teamId	TEXT NOT NULL,
                                gameId	TEXT NOT NULL,
                                team	TEXT NOT NULL,
                                name	TEXT NOT NULL,
                                atBats	int,
                                plateAppearances	int,
                                caughtStealing	int,
                                doubles	int,
                                earnedRuns	int,
                                groundIntoDp	int,
                                hits	int,
                                hitsAllowed	int,
                                homeRuns	int,
                                losses	int,
                                outsRecorded	int,
                                rbis	int,
                                runs	int,
                                stolenBases	int,
                                strikeouts	int,
                                struckouts	int,
                                triples	int,
                                walks	int,
                                walksIssued	int,
                                wins	int,
                                hitByPitch	int,
                                hitBatters	int,
                                quadruples	int,
                                pitchesThrown	int,
                                rotation_changed	boolean,
                                position	text,
                                rotation	int,
                                shutout	boolean,
                                noHitter	boolean,
                                perfectGame	boolean,
                                PRIMARY KEY(id)
                            );""")
        c.execute("""CREATE TABLE IF NOT EXISTS DailyGameResultsTable (
                                                id	INTEGER NOT NULL PRIMARY KEY,
                                                season	INTEGER NOT NULL,
                                                day	INTEGER NOT NULL,
                                                gameid	TEXT NOT NULL,
                                                hometeamid	TEXT NOT NULL,
                                                hometeamodds	REAL NOT NULL,
                                                hometeamshutoutpercentage	REAL NOT NULL,
                                                hometeamwin	BOOLEAN NOT NULL,
                                                hometeamwinpercentage	REAL NOT NULL,
                                                awayteamid	TEXT NOT NULL,
                                                awayteamodds	REAL NOT NULL,
                                                awayteamshutoutpercentage	REAL NOT NULL,
                                                awayteamwin	BOOLEAN NOT NULL,
                                                awayteamwinpercentage	REAL NOT NULL,
                                                upset	BOOLEAN NOT NULL,
                                                weather	INTEGER NOT NULL);""")
        c.execute("""CREATE TABLE IF NOT EXISTS PlayerLeagueAndStars (
                                                id INTEGER NOT NULL PRIMARY KEY,
                                                player_id TEXT NOT NULL,
                                                player_name TEXT NOT NULL,
                                                combined_stars REAL NOT NULL,
                                                baserunning_rating REAL NOT NULL,
                                                pitching_rating REAL NOT NULL,
                                                hitting_rating REAL NOT NULL,
                                                defense_rating REAL NOT NULL,
                                                team_id TEXT NOT NULL,
                                                team_name TEXT NOT NULL,
                                                league TEXT NOT NULL,
                                                division TEXT NOT NULL,
                                                position TEXT NOT NULL,
                                                slot INTEGER NOT NULL,
                                                elsewhere BOOLEAN NOT NULL,
                                                shelled BOOLEAN NOT NULL
        );""")
        try:
            c.execute("ALTER TABLE DailyStatSheets ADD COLUMN homeRunsAllowed	INTEGER DEFAULT 0;")
        except Exception as e:
            pass
        try:
            c.execute("ALTER TABLE PlayerLeagueAndStars ADD COLUMN position TEXT NOT NULL DEFAULT 'Lineup';")
            c.execute("ALTER TABLE PlayerLeagueAndStars ADD COLUMN slot INTEGER NOT NULL DEFAULT 1;")
            c.execute("ALTER TABLE PlayerLeagueAndStars ADD COLUMN elsewhere BOOLEAN NOT NULL DEFAULT 'false';")
            c.execute("ALTER TABLE PlayerLeagueAndStars ADD COLUMN shelled BOOLEAN NOT NULL DEFAULT 'false';")
            c.execute("ALTER TABLE PlayerLeagueAndStars ADD COLUMN legendary BOOLEAN NOT NULL DEFAULT 'false';")
        except Exception as e:
            print(f"Failed to modify PlayerLeagueAndStars table with error: '{e}'")
        try:
            c.execute("ALTER TABLE DailyStatSheets ADD COLUMN plateAppearances	INTEGER DEFAULT 0;")
        except Exception as e:
            print(f"Failed to modify DailyStatSheets table with error: '{e}'")
        c.close()


class SnaxInstance:
    def __init__(self, user_id, snake_oil, fresh_popcorn, stale_popcorn,
                 chips, burger, hot_dog, seeds, pickles, slushies, wet_pretzel,
                 doughnut, sundae, breakfast, lemonade, taffy, meatball):
        self.user_id = user_id
        self.snake_oil = snake_oil
        self.fresh_popcorn = fresh_popcorn
        self.stale_popcorn = stale_popcorn
        self.chips = chips
        self.burger = burger
        self.hot_dog = hot_dog
        self.seeds = seeds
        self.pickles = pickles
        self.slushies = slushies
        self.wet_pretzel = wet_pretzel
        self.doughnut = doughnut
        self.sundae = sundae
        self.breakfast = breakfast
        self.lemonade = lemonade
        self.taffy = taffy
        self.meatball = meatball

    def get_as_dict(self):
        return {'hot_dog': self.hot_dog, 'seeds': self.seeds, 'pickles': self.pickles,
                'slushies': self.slushies, 'wet_pretzel': self.wet_pretzel, 'snake_oil': self.snake_oil,
                'fresh_popcorn': self.fresh_popcorn, "stale_popcorn": self.stale_popcorn,
                "burger": self.burger, "chips": self.chips, 'doughnut': self.doughnut,
                'sundae': self.sundae, 'breakfast': self.breakfast, 'lemonade': self.lemonade,
                'taffy': self.taffy, 'meatball': self.meatball}


class PlayerStatSheetsInstance:
    def __init__(self, id, season, day, playerId, teamId, gameId, team, name, atBats, caughtStealing, doubles,
                 earnedRuns, groundIntoDp, hits, hitsAllowed, homeRuns, losses, outsRecorded, rbis, runs,
                 stolenBases, strikeouts, struckouts, triples, walks, walksIssued, wins, hitByPitch, hitBatters,
                 quadruples, pitchesThrown, rotation_changed, position, rotation, shutout,
                 noHitter, perfectGame, homeRunsAllowed):
        self.id = id
        self.season = season
        self.day = day
        self.playerId = playerId
        self.teamId = teamId
        self.gameId = gameId
        self.team = team
        self.name = name
        self.atBats = atBats
        self.caughtStealing = caughtStealing
        self.doubles = doubles
        self.earnedRuns = earnedRuns
        self.groundIntoDp = groundIntoDp
        self.hits = hits
        self.hitsAllowed = hitsAllowed
        self.homeRuns = homeRuns
        self.losses = losses
        self.outsRecorded = outsRecorded
        self.rbis = rbis
        self.runs = runs
        self.stolenBases = stolenBases
        self.strikeouts = strikeouts
        self.struckouts = struckouts
        self.triples = triples
        self.walks = walks
        self.walksIssued = walksIssued
        self.wins = wins
        self.hitByPitch = hitByPitch
        self.hitBatters = hitBatters
        self.quadruples = quadruples
        self.pitchesThrown = pitchesThrown
        self.rotation_changed = rotation_changed
        self.position = position
        self.rotation = rotation
        self.shutout = shutout
        self.noHitter = noHitter
        self.perfectGame = perfectGame
        self.homeRunsAllowed = homeRunsAllowed

    def get_as_dict(self):
        return {{"id": self.id, "season": self.season, "day": self.day, "playerId": self.playerId,
                 "teamId": self.teamId, "gameId": self.gameId, "team": self.team, "name": self.name,
                 "atBats": self.atBats, "caughtStealing": self.caughtStealing, "doubles": self.doubles,
                 "earnedRuns": self.earnedRuns, "groundIntoDp": self.groundIntoDp, "hits": self.hits,
                 "hitsAllowed": self.hitsAllowed, "homeRuns": self.homeRuns, "losses": self.losses,
                 "outsRecorded": self.outsRecorded,
                 "rbis": self.rbis, "runs": self.runs, "stolenBases": self.stolenBases, "strikeouts": self.strikeouts,
                 "struckouts": self.struckouts, "triples": self.triples, "walks": self.walks,
                 "walksIssued": self.walksIssued, "wins": self.wins, "hitByPitch": self.hitByPitch,
                 "hitBatters": self.hitBatters, "quadruples": self.quadruples, "pitchesThrown": self.pitchesThrown,
                 "rotation_changed": self.rotation_changed, "position": self.position, "rotation": self.rotation,
                 "shutout": self.shutout, "noHitter": self.noHitter,
                 "perfectGame": self.perfectGame, "homeRunsAllowed": self.homeRunsAllowed}}


class CycleInstance:
    def __init__(self, playerId, teamId, gameId, name, hits, doubles, triples, quadruples, homeRuns, atBats, Id):
        self.playerId = playerId
        self.teamId = teamId
        self.gameId = gameId
        self.name = name
        self.hits = hits
        self.doubles = doubles
        self.triples = triples
        self.quadruples = quadruples
        self.homeRuns = homeRuns
        self.atBats = atBats
        self.Id = Id
