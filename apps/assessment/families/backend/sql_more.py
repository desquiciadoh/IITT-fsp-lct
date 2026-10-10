"""SQL families for backend and ML & Data: typed answers, in-memory sqlite3 oracles.

bm.sql.left_join_count.v1  rows of a LEFT JOIN + GROUP BY, with the filter in ON or in WHERE
bm.sql.null_aggregates.v1  COUNT(*), COUNT(col), SUM, AVG over a column with NULLs
bm.sql.not_in_null.v1      NOT IN over a subquery that may contain NULL, vs NOT EXISTS

The generator evaluates the SQL semantics in Python; the oracle runs the script the candidate
sees in sqlite3 (same semantics as PostgreSQL for these constructs).
"""
from __future__ import annotations

import sqlite3

from ..base import FamilyMeta
from ..builder import TypedNumberFamily

BM = ("backend", "ml_data")
CITIES = ("Казань", "Омск", "Пермь", "Сочи", "Тула", "Уфа", "Тверь", "Самара")
PEOPLE = ("Анна", "Борис", "Вера", "Глеб", "Дина", "Егор", "Жанна", "Захар", "Ира", "Кирилл", "Лена", "Марк")


def _run_scalar(script: str):
    """Execute everything before the last SELECT, then return the SELECT's first column(s)."""
    setup, _, query = script.rpartition("\n\nSELECT ")
    db = sqlite3.connect(":memory:")
    try:
        db.executescript(setup)
        return db.execute("SELECT " + query).fetchall()
    finally:
        db.close()


def _sql_literal(v) -> str:
    return "NULL" if v is None else (f"'{v}'" if isinstance(v, str) else str(v))


class LeftJoinCount(TypedNumberFamily):
    """b = 0.2 (lower middle): LEFT JOIN keeps customers without orders; a filter on the right
    table in WHERE silently turns it into an inner join, while the same filter in ON keeps them.
    COUNT(o.id) counts matches, not rows."""

    meta = FamilyMeta(id="bm.sql.left_join_count.v1", version=1, specs=BM, topic="sql.joins",
                      skills=("sql",), format="sql_result", a=1.3, b=0.2, c=0.0, time_limit_s=150)

    def draw(self, rng):
        names = rng.sample(PEOPLE, rng.randint(4, 6))
        customers = [[i + 1, n, rng.choice(CITIES)] for i, n in enumerate(names)]
        orders = []
        for oid in range(1, rng.randint(5, 9) + 1):
            orders.append([oid, rng.randint(1, len(customers)), rng.randrange(5, 100, 5) * 100])
        amounts = sorted({o[2] for o in orders})
        threshold = amounts[rng.randrange(len(amounts))]
        return {"customers": customers, "orders": orders, "threshold": threshold,
                "where": rng.random() < 0.5, "ask": rng.choice(("rows", "zero"))}

    def solve(self, p):
        rows = []
        for cid, _, _ in p["customers"]:
            matched = [o for o in p["orders"] if o[1] == cid and o[2] >= p["threshold"]]
            if p["where"]:
                if matched:
                    rows.append(len(matched))      # WHERE drops customers whose only rows are NULL
            else:
                rows.append(len(matched))          # ON keeps every customer; COUNT(o.id) may be 0
        return len(rows) if p["ask"] == "rows" else sum(1 for r in rows if r == 0)

    def render(self, p):
        cust = ",\n".join(f"  ({c[0]}, '{c[1]}', '{c[2]}')" for c in p["customers"])
        ords = ",\n".join(f"  ({o[0]}, {o[1]}, {o[2]})" for o in p["orders"])
        cond = f"o.amount >= {p['threshold']}"
        join = (f"LEFT JOIN orders o ON o.customer_id = c.id\nWHERE {cond}" if p["where"]
                else f"LEFT JOIN orders o ON o.customer_id = c.id AND {cond}")
        script = ("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, city TEXT);\n"
                  f"INSERT INTO customers VALUES\n{cust};\n"
                  "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, amount INTEGER);\n"
                  f"INSERT INTO orders VALUES\n{ords};\n\n"
                  f"SELECT c.name, COUNT(o.id) AS n_orders\nFROM customers c\n{join}\nGROUP BY c.id, c.name;")
        question = ("Сколько строк вернёт SELECT-запрос в конце скрипта?" if p["ask"] == "rows" else
                    "В скольких строках результата SELECT-запроса в конце скрипта `n_orders` = 0?")
        return question, {"lang": "sql", "text": script}

    def oracle_value(self, inst):
        rows = _run_scalar(inst.code["text"])
        return float(len(rows) if "Сколько строк" in inst.stem_md else sum(1 for r in rows if r[1] == 0))


class NullAggregates(TypedNumberFamily):
    """b = -0.2 (upper junior): aggregate functions skip NULL (COUNT(col), SUM, AVG) while
    COUNT(*) counts rows; AVG divides by the non-NULL count, not by all rows."""

    meta = FamilyMeta(id="bm.sql.null_aggregates.v1", version=1, specs=BM, topic="sql.aggregation",
                      skills=("sql",), format="sql_result", a=1.2, b=-0.2, c=0.0, time_limit_s=120)
    DECIMALS = 2
    AGGS = ("COUNT(*)", "COUNT(bonus)", "SUM(bonus)", "AVG(bonus)")

    def draw(self, rng):
        n = rng.randint(6, 10)
        rows = []
        for i in range(n):
            bonus = None if rng.random() < 0.35 else rng.randrange(1, 40) * 500
            rows.append([i + 1, rng.choice(PEOPLE), rng.choice(("dev", "qa", "ops")), bonus])
        if all(r[3] is None for r in rows):
            rows[0][3] = 5000
        team = rng.choice(("dev", "qa", "ops", None))
        if team and not any(r[2] == team and r[3] is not None for r in rows):
            team = None
        return {"rows": rows, "agg": rng.choice(self.AGGS), "team": team}

    def solve(self, p):
        rows = [r for r in p["rows"] if p["team"] is None or r[2] == p["team"]]
        vals = [r[3] for r in rows if r[3] is not None]
        agg = p["agg"]
        if agg == "COUNT(*)":
            return len(rows)
        if agg == "COUNT(bonus)":
            return len(vals)
        if agg == "SUM(bonus)":
            return sum(vals)
        return sum(vals) / len(vals)

    def render(self, p):
        values = ",\n".join(f"  ({r[0]}, '{r[1]}', '{r[2]}', {_sql_literal(r[3])})" for r in p["rows"])
        where = f"\nWHERE team = '{p['team']}'" if p["team"] else ""
        script = ("CREATE TABLE staff (id INTEGER PRIMARY KEY, name TEXT, team TEXT, bonus INTEGER);\n"
                  f"INSERT INTO staff VALUES\n{values};\n\n"
                  f"SELECT {p['agg']}\nFROM staff{where};")
        return "Какое значение вернёт SELECT-запрос в конце скрипта?", {"lang": "sql", "text": script}

    def oracle_value(self, inst):
        return float(_run_scalar(inst.code["text"])[0][0])


class NotInNull(TypedNumberFamily):
    """b = 1.2 (senior): `x NOT IN (subquery)` is unknown for every x when the subquery returns a
    NULL, so the query returns nothing; NOT EXISTS ignores the NULL. Classic production trap."""

    meta = FamilyMeta(id="bm.sql.not_in_null.v1", version=1, specs=BM, topic="sql.joins",
                      skills=("sql",), format="sql_result", a=1.4, b=1.2, c=0.0, time_limit_s=150)

    def draw(self, rng):
        users = list(range(1, rng.randint(6, 10) + 1))
        banned = rng.sample(users, rng.randint(1, 3))
        if rng.random() < 0.5:
            banned = [*banned, None]
        rng.shuffle(banned)
        return {"users": users, "names": [rng.choice(PEOPLE) for _ in users], "banned": banned,
                "form": rng.choice(("not_in", "not_exists"))}

    def solve(self, p):
        ids = [b for b in p["banned"] if b is not None]
        if p["form"] == "not_in" and None in p["banned"]:
            return 0
        return sum(1 for u in p["users"] if u not in ids)

    def render(self, p):
        users = ",\n".join(f"  ({u}, '{n}')" for u, n in zip(p["users"], p["names"], strict=True))
        banned = ",\n".join(f"  ({_sql_literal(b)})" for b in p["banned"])
        cond = ("u.id NOT IN (SELECT user_id FROM banned)" if p["form"] == "not_in" else
                "NOT EXISTS (SELECT 1 FROM banned b WHERE b.user_id = u.id)")
        script = ("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);\n"
                  f"INSERT INTO users VALUES\n{users};\n"
                  "CREATE TABLE banned (user_id INTEGER);\n"
                  f"INSERT INTO banned VALUES\n{banned};\n\n"
                  f"SELECT COUNT(*)\nFROM users u\nWHERE {cond};")
        return "Какое число вернёт SELECT-запрос в конце скрипта?", {"lang": "sql", "text": script}

    def oracle_value(self, inst):
        return float(_run_scalar(inst.code["text"])[0][0])


FAMILIES = [LeftJoinCount(), NullAggregates(), NotInNull()]
