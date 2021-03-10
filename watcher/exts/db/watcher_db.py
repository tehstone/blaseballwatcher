from playhouse.apsw_ext import *
from playhouse.migrate import *


class WatcherDB:
    _db = Proxy()
    _migrator = None
    @classmethod
    def start(cls, db_path):
        handle = APSWDatabase(db_path, pragmas={
            'journal_mode': 'wal',
            'cache_size': -1 * 64000,
            'foreign_keys': 1,
            'ignore_check_constraints': 0
        })
        cls._db.initialize(handle)
        # ensure db matches current schema
        cls._db.create_tables([RulesBlogTable, UserSnaxIgnoreTable, UserSnaxTable])
        cls.init()
        cls._migrator = SqliteMigrator(cls._db)

    @classmethod
    def stop(cls):
        return cls._db.close()

    @classmethod
    def init(cls):
        pass


class BaseModel(Model):
    class Meta:
        database = WatcherDB._db


class RulesBlogTable(BaseModel):
    pull_date = DateTimeField()
    page_text = TextField(index=True)


class UserSnaxTable(BaseModel):
    user_id = BigIntegerField(index=True)
    snake_oil = IntegerField(null=True, default=0)
    fresh_popcorn = IntegerField(null=True, default=0)
    stale_popcorn = IntegerField(null=True, default=0)
    chips = IntegerField(null=True, default=0)
    burger = IntegerField(null=True, default=0)
    hot_dog = IntegerField(null=True, default=0)
    seeds = IntegerField(null=True, default=0)
    pickles = IntegerField(null=True, default=0)
    slushies = IntegerField(null=True, default=0)
    wet_pretzel = IntegerField(null=True, default=0)


class UserSnaxIgnoreTable(BaseModel):
    user_id = BigIntegerField(index=True)
    ignore_list = TextField(default="")


class SnaxInstance:
    def __init__(self, user_id, snake_oil, fresh_popcorn, stale_popcorn,
                 chips, burger, hot_dog, seeds, pickles, slushies, wet_pretzel):
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

    def get_as_dict(self):
        return {'hot_dog': self.hot_dog, 'seeds': self.seeds, 'pickles': self.pickles,
                'slushies': self.slushies, 'wet_pretzel': self.wet_pretzel, 'snake_oil': self.snake_oil,
                'fresh': self.fresh_popcorn, "stale": self.stale_popcorn,
                "burgers": self.burger, "chips": self.chips}

