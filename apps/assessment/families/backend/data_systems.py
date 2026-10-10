"""Backend families on transactions, concurrency and capacity.

be.db.isolation_anomaly.v1  name the anomaly a two-transaction schedule shows (classification)
be.db.lost_update.v1        final balance after interleaved read-modify-write transactions (typed)
be.async.gather_time.v1     total run time of an asyncio main() with await/gather/create_task (typed)
be.async.semaphore_time.v1  total time of N tasks behind asyncio.Semaphore(k) (typed)
be.sys.littles_law.v1       concurrency or workers needed from throughput and latency (typed)
be.sys.cache_latency.v1     mean latency with a cache in front of the database (typed)

Oracles re-read the rendered schedule, program or numbers and recompute by a different method
(an interpreter for the schedule, a heap-based scheduler, Fraction arithmetic).
"""
from __future__ import annotations

import heapq
import re
from fractions import Fraction

from ..base import FamilyMeta, Instance
from ..builder import ClassificationFamily, TypedNumberFamily

B = ("backend",)
TABLES = ("accounts", "wallets", "stock", "seats", "balances", "limits", "quotas", "inventory")


# ── isolation anomalies ────────────────────────────────────────────────────

class IsolationAnomaly(ClassificationFamily):
    """b = 0.4 (middle): telling a dirty read from a non-repeatable read, a phantom and a lost
    update from a concrete schedule. Was 1.1; the ML-6 review lowered it, because one surface
    marker (ROLLBACK, INSERT, two UPDATEs) decides the class and the read values are annotated,
    so it is easier than lost_update (b = 0.5). Uniqueness is only the label and the order of the
    two transactions (8 questions): ids and amounts are decoration, so it is exempt from the
    collision gate as a concept item (verify.CONCEPT_FAMILIES)."""

    meta = FamilyMeta(id="be.db.isolation_anomaly.v1", version=1, specs=B, topic="backend.databases",
                      skills=("postgresql", "sql"), format="concept_mcq", a=1.3, b=0.4, c=0.25, time_limit_s=150)
    LABELS = ("Грязное чтение", "Неповторяющееся чтение", "Фантомное чтение", "Потерянное обновление")
    SEMANTIC = ("first",)

    def draw(self, rng, label):
        return {"table": rng.choice(TABLES), "id": rng.randint(1, 999), "x": rng.randint(5, 90) * 10,
                "d1": rng.randint(1, 9) * 10, "d2": rng.randint(1, 9) * 10, "flag": rng.randint(1, 4),
                "cnt": rng.randint(2, 30), "first": rng.choice(("T1", "T2"))}

    def _steps(self, p):
        t, i, x, d1, d2 = p["table"], p["id"], p["x"], p["d1"], p["d2"]
        a, b = ("T1", "T2") if p["first"] == "T1" else ("T2", "T1")
        sel = f"SELECT amount FROM {t} WHERE id = {i}"
        label = p["label"]
        if label == "Грязное чтение":
            return [(b, "BEGIN"), (b, f"UPDATE {t} SET amount = {x + d1} WHERE id = {i}"), (a, "BEGIN"),
                    (a, f"{sel}  -- получила {x + d1}"), (b, "ROLLBACK"), (a, "COMMIT")]
        if label == "Неповторяющееся чтение":
            return [(a, "BEGIN"), (a, f"{sel}  -- получила {x}"), (b, "BEGIN"),
                    (b, f"UPDATE {t} SET amount = {x + d1} WHERE id = {i}"), (b, "COMMIT"),
                    (a, f"{sel}  -- получила {x + d1}"), (a, "COMMIT")]
        if label == "Фантомное чтение":
            cnt = p["cnt"]
            return [(a, "BEGIN"), (a, f"SELECT COUNT(*) FROM {t} WHERE flag = {p['flag']}  -- получила {cnt}"),
                    (b, "BEGIN"), (b, f"INSERT INTO {t} (id, amount, flag) VALUES ({i}, {x}, {p['flag']})"),
                    (b, "COMMIT"), (a, f"SELECT COUNT(*) FROM {t} WHERE flag = {p['flag']}  -- получила {cnt + 1}"),
                    (a, "COMMIT")]
        return [(a, "BEGIN"), (a, f"{sel}  -- получила {x}"), (b, "BEGIN"), (b, f"{sel}  -- получила {x}"),
                (a, f"UPDATE {t} SET amount = {x + d1} WHERE id = {i}  -- {x} + {d1}"), (a, "COMMIT"),
                (b, f"UPDATE {t} SET amount = {x + d2} WHERE id = {i}  -- {x} + {d2}"), (b, "COMMIT")]

    def render(self, p):
        rows = "\n".join(f"{n}. {who}: {sql}" for n, (who, sql) in enumerate(self._steps(p), start=1))
        return ("Две транзакции выполняются параллельно в порядке шагов ниже (без блокировок строк). "
                "Какую аномалию показывает это расписание?", {"lang": "sql", "text": rows})

    def classify(self, inst: Instance):
        text = inst.code["text"]
        if "ROLLBACK" in text:
            return "Грязное чтение"
        if "INSERT" in text:
            return "Фантомное чтение"
        if len(re.findall(r"UPDATE", text)) == 2:
            return "Потерянное обновление"
        reads = re.findall(r"получила (\d+)", text)
        return "Неповторяющееся чтение" if len(reads) == 2 and reads[0] != reads[1] else None


# ── lost update arithmetic ─────────────────────────────────────────────────

class LostUpdate(TypedNumberFamily):
    """b = 0.5 (middle): two or three read-modify-write transactions interleave without locks;
    each write uses the value its own transaction read earlier, so some deltas vanish."""

    meta = FamilyMeta(id="be.db.lost_update.v1", version=1, specs=B, topic="backend.databases",
                      skills=("postgresql", "sql"), format="numeric_scenario", a=1.3, b=0.5, c=0.0,
                      time_limit_s=150)
    SEMANTIC = ("start", "deltas", "events")

    def draw(self, rng):
        n_tx = rng.randint(2, 3)
        deltas = [rng.choice((1, -1)) * rng.randint(1, 30) * 10 for _ in range(n_tx)]
        events = [(t, "read") for t in range(n_tx)] + [(t, "write") for t in range(n_tx)]
        while True:
            rng.shuffle(events)
            if all(events.index((t, "read")) < events.index((t, "write")) for t in range(n_tx)):
                break
        return {"start": rng.randint(10, 99) * 10, "deltas": deltas, "events": [list(e) for e in events],
                "table": rng.choice(TABLES), "id": rng.randint(1, 999)}

    def solve(self, p):
        db, local = p["start"], {}
        for t, kind in p["events"]:
            if kind == "read":
                local[t] = db
            else:
                db = local[t] + p["deltas"][t]
        return db

    def render(self, p):
        t, i = p["table"], p["id"]
        lines = []
        for n, (tx, kind) in enumerate(p["events"], start=1):
            name = f"T{tx + 1}"
            if kind == "read":
                lines.append(f"{n}. {name}: v := SELECT amount FROM {t} WHERE id = {i}")
            else:
                d = p["deltas"][tx]
                sign = "+" if d >= 0 else "-"
                lines.append(f"{n}. {name}: UPDATE {t} SET amount = v {sign} {abs(d)} WHERE id = {i}; COMMIT")
        return (f"Перед началом amount = {p['start']}. Транзакции (каждая со своей переменной v) выполняются "
                "в порядке шагов ниже, без блокировок. Чему равен amount после всех шагов?",
                {"lang": "sql", "text": "\n".join(lines)})

    def oracle_value(self, inst):
        db = int(re.findall(r"amount = (-?\d+)\.", inst.stem_md)[0])
        local: dict[str, int] = {}
        for line in inst.code["text"].split("\n"):
            tx = re.findall(r"(T\d):", line)[0]
            if "SELECT" in line:
                local[tx] = db
            else:
                sign, num = re.findall(r"v ([+-]) (\d+)", line)[0]
                db = local[tx] + (int(num) if sign == "+" else -int(num))
        return float(db)


# ── asyncio timing ─────────────────────────────────────────────────────────

class GatherTime(TypedNumberFamily):
    """b = 0.3 (lower middle): `await` runs coroutines one after another, `gather` runs them
    together (time of the longest), a task started with create_task runs in the background
    until awaited."""

    meta = FamilyMeta(id="be.async.gather_time.v1", version=1, specs=B, topic="backend.concurrency",
                      skills=("asyncio", "python"), format="code_output", a=1.3, b=0.3, c=0.0, time_limit_s=120)
    SEMANTIC = ("stmts",)

    def draw(self, rng):
        stmts, tasks = [], 0
        for _ in range(rng.randint(3, 6)):
            kind = rng.choice(("await", "gather", "task", "await_task") if tasks else ("await", "gather", "task"))
            if kind == "await":
                stmts.append(["await", rng.randint(1, 9)])
            elif kind == "gather":
                stmts.append(["gather", [rng.randint(1, 9) for _ in range(rng.randint(2, 4))]])
            elif kind == "task":
                stmts.append(["task", tasks, rng.randint(2, 12)])
                tasks += 1
            else:
                stmts.append(["await_task", rng.randrange(tasks)])
        for t in range(tasks):                      # every task is awaited before main returns
            if not any(s[0] == "await_task" and s[1] == t for s in stmts):
                stmts.append(["await_task", t])
        return {"stmts": stmts, "fn": rng.choice(("job", "fetch", "work", "load", "call", "ping", "sync", "pull",
                                                  "push", "step"))}

    def solve(self, p):
        now, ends = 0, {}
        for s in p["stmts"]:
            if s[0] == "await":
                now += s[1]
            elif s[0] == "gather":
                now += max(s[1])
            elif s[0] == "task":
                ends[s[1]] = now + s[2]
            else:
                now = max(now, ends[s[1]])
        return now

    def render(self, p):
        fn = p["fn"]
        lines = ["import asyncio", "", "", f"async def {fn}(seconds):", "    await asyncio.sleep(seconds)", "", "",
                 "async def main():"]
        for s in p["stmts"]:
            if s[0] == "await":
                lines.append(f"    await {fn}({s[1]})")
            elif s[0] == "gather":
                lines.append(f"    await asyncio.gather({', '.join(f'{fn}({d})' for d in s[1])})")
            elif s[0] == "task":
                lines.append(f"    t{s[1]} = asyncio.create_task({fn}({s[2]}))")
            else:
                lines.append(f"    await t{s[1]}")
        lines += ["", "", "asyncio.run(main())"]
        return ("Сколько секунд (без учёта накладных расходов) выполняется `main()`?",
                {"lang": "python", "text": "\n".join(lines)})

    def oracle_value(self, inst):
        """Event simulation: every coroutine is a timer; the main line advances to each timer it waits for."""
        now, started = 0, {}
        for line in inst.code["text"].split("main():")[1].split("\n"):
            line = line.strip()
            if m := re.match(r"(t\d+) = asyncio\.create_task\(\w+\((\d+)\)\)", line):
                started[m.group(1)] = now + int(m.group(2))
            elif line.startswith("await asyncio.gather("):
                now = max(now + int(d) for d in re.findall(r"\w+\((\d+)\)", line[len("await asyncio.gather("):]))
            elif m := re.match(r"await (t\d+)$", line):
                now = max(now, started[m.group(1)])
            elif m := re.match(r"await \w+\((\d+)\)$", line):
                now += int(m.group(1))
        return float(now)


class SemaphoreTime(TypedNumberFamily):
    """b = 1.3 (senior): with Semaphore(k) at most k sleeps overlap; tasks enter in creation order
    as slots free up, so the total is a small scheduling exercise, not max() or sum()."""

    meta = FamilyMeta(id="be.async.semaphore_time.v1", version=1, specs=B, topic="backend.concurrency",
                      skills=("asyncio", "python"), format="code_output", a=1.4, b=1.3, c=0.0, time_limit_s=150)
    SEMANTIC = ("k", "durations")

    def draw(self, rng):
        return {"k": rng.randint(2, 3), "durations": [rng.randint(1, 12) for _ in range(rng.randint(5, 8))],
                "fn": rng.choice(("download", "process", "upload", "resize", "query", "render", "scan", "sync",
                                  "export", "notify"))}

    def solve(self, p):
        free = [0] * p["k"]                          # slot free times; tasks start in order
        end = 0
        for d in p["durations"]:
            slot = min(range(p["k"]), key=lambda i: (free[i], i))
            free[slot] += d
            end = max(end, free[slot])
        return end

    def render(self, p):
        fn = p["fn"]
        lines = ["import asyncio", "", f"sem = asyncio.Semaphore({p['k']})", "", "",
                 f"async def {fn}(seconds):", "    async with sem:", "        await asyncio.sleep(seconds)", "", "",
                 "async def main():",
                 f"    await asyncio.gather({', '.join(f'{fn}({d})' for d in p['durations'])})", "", "",
                 "asyncio.run(main())"]
        return ("Задачи в `gather` стартуют в порядке перечисления. Сколько секунд выполняется `main()`?",
                {"lang": "python", "text": "\n".join(lines)})

    def oracle_value(self, inst):
        """Discrete-event simulation with a heap of running tasks and a FIFO wait queue."""
        text = inst.code["text"]
        k = int(re.findall(r"Semaphore\((\d+)\)", text)[0])
        gather = text.split("gather(")[1].split(")\n")[0]
        waiting = [int(d) for d in re.findall(r"\w+\((\d+)\)", gather)]
        running: list[int] = []
        now = 0
        while waiting or running:
            while waiting and len(running) < k:
                heapq.heappush(running, now + waiting.pop(0))
            now = heapq.heappop(running)
        return float(now)


# ── capacity ───────────────────────────────────────────────────────────────

class LittlesLaw(TypedNumberFamily):
    """b = 0.6 (middle): Little's law L = λ·W with ms -> s; the unit conversion is the usual slip.
    The worker variant (divide by utilisation, round up) was dropped in the ML-6 review: its
    "whole number of workers" contradicted the one-decimal hint. b moved from 0.8 with it."""

    meta = FamilyMeta(id="be.sys.littles_law.v1", version=1, specs=B, topic="backend.system_design",
                      skills=("microservices",), format="numeric_scenario", a=1.2, b=0.6, c=0.0, time_limit_s=120)
    DECIMALS = 1
    SEMANTIC = ("rps", "ms")

    def draw(self, rng):
        return {"rps": rng.randint(20, 2000) * 5, "ms": rng.randint(5, 900),
                "svc": rng.choice(("API заказов", "сервис поиска", "платёжный шлюз", "сервис рекомендаций",
                                   "сервис авторизации", "API каталога"))}

    def solve(self, p):
        return p["rps"] * p["ms"] / 1000

    def render(self, p):
        head = (f"{p['svc'][0].upper()}{p['svc'][1:]} получает в среднем {p['rps']} запросов в секунду, "
                f"среднее время обработки одного запроса — {p['ms']} мс.")
        return f"{head} Сколько запросов в среднем обрабатывается одновременно?", None

    def oracle_value(self, inst):
        rps, ms = (int(x) for x in re.findall(r"(\d+) запросов в секунду.*?(\d+) мс", inst.stem_md)[0])
        return float(Fraction(rps) * Fraction(ms, 1000))


def _ru(x: float) -> str:
    """12.5 -> '12,5', 12.0 -> '12' (Russian decimal comma)."""
    return f"{x:g}".replace(".", ",")


DBS = (("PostgreSQL", "PostgreSQL"), ("MySQL", "MySQL"), ("внешним API", "внешнему API"),
       ("ClickHouse", "ClickHouse"))


class CacheLatency(TypedNumberFamily):
    """b = -0.4 (upper junior): a weighted average where a miss costs the cache lookup plus the
    database; forgetting the lookup on a miss is the common slip."""

    meta = FamilyMeta(id="be.sys.cache_latency.v1", version=1, specs=B, topic="backend.system_design",
                      skills=("redis",), format="numeric_scenario", a=1.0, b=-0.4, c=0.0, time_limit_s=90)
    DECIMALS = 2
    SEMANTIC = ("hit", "cache_ms", "db_ms")

    def draw(self, rng):
        return {"hit": rng.randint(500, 990) / 10, "cache_ms": rng.randint(2, 40) / 2, "db_ms": rng.randint(8, 160) * 5,
                "store": rng.choice(("Redis", "Memcached", "локальный кэш")),
                "db": rng.randrange(len(DBS))}

    def solve(self, p):
        h = p["hit"] / 100
        return h * p["cache_ms"] + (1 - h) * (p["cache_ms"] + p["db_ms"])

    def render(self, p):
        before, to = DBS[p["db"]]
        return (f"Перед {before} стоит {p['store']}. Доля попаданий в кэш — {_ru(p['hit'])} %. Чтение из кэша "
                f"занимает {_ru(p['cache_ms'])} мс; при промахе сначала проверяется кэш, затем идёт запрос к "
                f"{to}, который занимает {p['db_ms']} мс. Каково среднее время чтения в мс?", None)

    def oracle_value(self, inst):
        hit, cache_ms, db_ms = (Fraction(x.replace(",", ".")) for x in re.findall(
            r"попаданий в кэш — ([\d,]+) %.*?занимает ([\d,]+) мс.*?занимает (\d+) мс", inst.stem_md)[0])
        # 100 reads: hit reads cost the cache, miss reads cost cache + database
        total = (hit * cache_ms + (100 - hit) * (cache_ms + db_ms)) / 100
        return float(total)


FAMILIES = [IsolationAnomaly(), LostUpdate(), GatherTime(), SemaphoreTime(), LittlesLaw(), CacheLatency()]
