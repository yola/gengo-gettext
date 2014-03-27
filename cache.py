import os
import sqlite3


db = None


class Job(object):
    def __init__(self, id, order_id, string, language, status):
        self.id = id
        self.order_id = order_id
        self.string = string
        self.language = language
        self.status = status

    def save(self):
        db = get_db()
        c = db.cursor()
        c.execute(
            """REPLACE INTO job (id, order_id, string, language, status)
               VALUES (?, ?, ?, ?, ?);""",
            (self.id, self.order_id, self.string, self.language, self.status))
        db.commit()

    @classmethod
    def find(cls, string, language):
        db = get_db()
        c = db.cursor()
        c.execute(
            """SELECT id, order_id, string, language, status FROM job
               WHERE string = ? AND language = ?;""", (string, language))
        row = c.fetchone()
        if row:
            return Job(*row)


class Order(object):
    def __init__(self, id, created):
        self.id = id
        self.created = created

    def save(self):
        db = get_db()
        c = db.cursor()
        c.execute('REPLACE INTO "order" (id, created) VALUES (?, ?);',
                  (self.id, self.created))
        db.commit()


def get_db():
    global db
    if not db:
        create_tables = not os.path.exists('jobs.db')
        db = sqlite3.connect('jobs.db')
        if create_tables:
            c = db.cursor()
            c.execute(
                """CREATE TABLE job
                   (id INTEGER PRIMARY KEY, order_id INTEGER, string TEXT,
                    language TEXT, status TEXT);""")
            c.execute(
                "CREATE INDEX job_lang_string ON job (language, string);")
            c.execute(
                """CREATE TABLE "order"
                   (id INTEGER PRIMARY KEY, created INTEGER);""")
            db.commit()
    return db


def latest_order():
    db = get_db()
    c = db.cursor()
    c.execute("""SELECT id, created FROM "order"
                 WHERE created = (SELECT MAX(created) FROM "order");""")
    row = c.fetchone()
    if row:
        return Order(*row)
