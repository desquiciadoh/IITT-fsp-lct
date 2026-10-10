"""be.sql.group_having.v2: the total `cnt` over the groups that survive WHERE, GROUP BY and HAVING.

The table rows, the WHERE threshold and the HAVING threshold are random, so the answer
(0..25) depends on the draw. Asking for the sum rather than the number of result rows keeps
the answer range wide: with only 0..5 possible counts, the set of four option values alone
gave the answer away (ML-1 review). The generator counts in Python; the oracle rebuilds the
table in an in-memory sqlite3 database from the SQL the candidate sees and runs the query.

Difficulty prior b = -0.3 (upper junior): one query on ~12 visible rows, but the candidate
must apply WHERE before grouping and use >= in HAVING.

Distractors. Ignoring WHERE, applying HAVING to the unfiltered counts, `>` for `>=`, ignoring
HAVING and counting result rows instead of summing cnt are the classic junior mistakes. On 15 %
of the items one of them (on a side drawn at random) is an option; every other distractor is
the answer of an independent redraw of the generator, so it has the answer's own
distribution. Two earlier designs leaked through the option values alone: a window around the
answer (58 %), and a misconception on every item, which pushed the answer to a middle rank
(33 % at every item, 30 % at a third of them). Every value- and rank-based strategy now
measures at chance + 0.02 at most.
"""
from __future__ import annotations

import random
import sqlite3

from ..base import FamilyMeta, Instance, fingerprint_of
from ..kit import choice_options, is_choice_correct, option_key_for_text

META = FamilyMeta(id="be.sql.group_having.v2", version=2, specs=("backend", "ml_data"),
                  topic="sql.aggregation", skills=("sql",), format="sql_result",
                  a=1.2, b=-0.3, c=0.25, time_limit_s=120)

MISCONCEPTION_SHARE = 0.15  # items that show one misconception value; at 1.0 the answer's
                            # rank leaks (0.33 vs a 0.305 gate), at 0.3 it sits at the gate (0.30)

SCHEMAS = (
    ("employees", "department", ("Sales", "Support", "Finance", "Legal", "Research", "Design", "Ops")),
    ("staff", "team", ("Alpha", "Bravo", "Delta", "Gamma", "Omega", "Sigma", "Zeta")),
    ("contractors", "city", ("Kazan", "Omsk", "Perm", "Sochi", "Tula", "Ufa", "Tver")),
)


class SqlGroupHaving:
    meta = META

    def generate(self, rng: random.Random) -> Instance:
        params, correct, mistakes = self._draw(rng)
        values = [correct]
        # One misconception value (when it differs from the answer) on MISCONCEPTION_SHARE of the
        # items; every other option is the answer of an independent redraw of the same generator.
        # Redraw answers have the answer's own distribution, so no single value, rank or
        # "typical size" points at the key (ML-1 review: windows around the answer leaked 58 %).
        # The side (above or below the answer) is drawn first: each misconception errs in a fixed
        # direction, so picking among all of them would push the answer's rank (verify gate).
        above = rng.random() < 0.5
        wrong = sorted({m for m in mistakes if (m > correct if above else m < correct)})
        if wrong and rng.random() < MISCONCEPTION_SHARE:
            values.append(wrong[rng.randrange(len(wrong))])
        while len(values) < 4:
            v = self._draw(rng)[1]
            if v not in values:
                values.append(v)
        options, key = choice_options(rng, str(correct), [str(v) for v in values[1:]])
        return Instance(
            stem_md=f"Дан SQL-скрипт с таблицей `{params['table']}`. Чему равна сумма значений "
                    "`cnt` по всем строкам, которые вернёт SELECT-запрос в конце скрипта? "
                    "Если запрос не вернёт ни одной строки, ответ 0.",
            input="choice", key=key, fingerprint=fingerprint_of(params),
            code={"lang": "sql", "text": _script(**params)}, options=options)

    @staticmethod
    def _draw(rng: random.Random):
        table, col, names = SCHEMAS[rng.randrange(len(SCHEMAS))]
        groups = sorted(rng.sample(names, rng.randint(3, 5)))
        rows = [(g, rng.randrange(60, 301, 5) * 1000) for g in groups for _ in range(rng.randint(1, 5))]
        rng.shuffle(rows)
        salaries = sorted({s for _, s in rows})
        where = salaries[rng.randrange(len(salaries) // 4, max(len(salaries) // 4 + 1, 3 * len(salaries) // 4))]
        having = rng.randint(1, 3)
        params = {"table": table, "col": col, "rows": rows, "where": where, "having": having}

        total = _counts(rows)
        after_where = _counts([r for r in rows if r[1] >= where])
        correct = sum(c for c in after_where.values() if c >= having)
        mistakes = [
            sum(c for c in total.values() if c >= having),                         # ignores WHERE
            sum(after_where.get(g, 0) for g, c in total.items() if c >= having),   # HAVING before WHERE
            sum(c for c in after_where.values() if c > having),                    # > instead of >=
            sum(after_where.values()),                                             # ignores HAVING
            sum(1 for c in after_where.values() if c >= having),                   # counts result rows
        ]
        return params, correct, mistakes

    def is_correct(self, key, answer: dict) -> bool:
        return is_choice_correct(key, answer)

    def oracle(self, inst: Instance):
        script = inst.code["text"]
        setup, _, query = script.rpartition("\n\nSELECT ")
        db = sqlite3.connect(":memory:")
        try:
            db.executescript(setup)
            n = sum(row[1] for row in db.execute("SELECT " + query).fetchall())
        finally:
            db.close()
        return option_key_for_text(inst.options, str(n))


def _unique(xs):
    out = []
    for x in xs:
        if x not in out:
            out.append(x)
    return out


def _counts(rows):
    out: dict[str, int] = {}
    for g, _ in rows:
        out[g] = out.get(g, 0) + 1
    return out


def _script(table, col, rows, where, having) -> str:  # noqa: PLR0913
    values = ",\n".join(f"  ('{g}', {s})" for g, s in rows)
    return (f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, {col} TEXT, salary INTEGER);\n"
            f"INSERT INTO {table} ({col}, salary) VALUES\n{values};\n\n"
            f"SELECT {col}, COUNT(*) AS cnt\nFROM {table}\nWHERE salary >= {where}\n"
            f"GROUP BY {col}\nHAVING COUNT(*) >= {having};")


FAMILY = SqlGroupHaving()
