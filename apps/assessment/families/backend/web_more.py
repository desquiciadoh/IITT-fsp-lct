"""Backend HTTP and security families added in ML-13 (they replace the retired classification
families status_code, method and vuln_class, whose few distinct questions leaked; see
registry.RETIRED). Typed answers; the oracle executes the program the candidate sees.

be.http.retry_backoff.v1   total wait of capped exponential backoff with jitter-free retries
be.http.token_bucket.v1    sum of the timestamps a token-bucket rate limiter accepts
be.sec.lockout.v1          sum of the timestamps rejected by a consecutive-failure lockout
be.sec.token_expiry.v1     sum of the ids of tokens valid at `now` with clock-skew leeway
"""
from __future__ import annotations

from ..base import FamilyMeta
from ..builder import TypedNumberFamily, run_python


def _meta(fid, topic, b, a=1.2, t=180, skills=("rest_api",)):
    return FamilyMeta(id=fid, version=1, specs=("backend",), topic=topic, skills=skills,
                      format="code_output", a=a, b=b, c=0.0, time_limit_s=t)


class _Exec(TypedNumberFamily):
    def oracle_value(self, inst):
        return float(run_python(inst.code["text"]))

    def render(self, p):
        return f"{self.STEM}\n\nЧто напечатает программа?", {"lang": "python", "text": self.program(p)}


class RetryBackoff(_Exec):
    """b = -0.3 (junior): delay = min(cap, base·2^attempt) before each retry; the cap, and the
    fact that a request that succeeds on attempt k waited k times (not k + 1), are where answers
    go wrong. Several requests fail a drawn number of times each."""
    meta = _meta("be.http.retry_backoff.v1", "backend.http", -0.3, a=1.1, t=150)
    SEMANTIC = ("base", "cap", "fails")
    STEM = ("Клиент повторяет запросы к нестабильному API с экспоненциальной задержкой. "
            "`fails` — сколько раз подряд падает каждый запрос перед успешным ответом.")

    def draw(self, rng):
        while True:
            p = {"base": rng.randrange(20, 310, 10), "cap": rng.randrange(300, 2100, 100),
                 "fails": [rng.randint(0, 5) for _ in range(rng.randint(3, 4))]}
            uncapped = sum(p["base"] * 2 ** i for f in p["fails"] for i in range(f))
            if 0 < self.solve(p) != uncapped:          # the cap must matter
                return p

    def solve(self, p):
        return sum(min(p["cap"], p["base"] * 2 ** i) for f in p["fails"] for i in range(f))

    def program(self, p):
        return (f"BASE_MS, CAP_MS = {p['base']}, {p['cap']}\nfails = {p['fails']}\n\n"
                "waited = 0\nfor n_fail in fails:\n    attempt = 0\n    while True:\n"
                "        ok = attempt >= n_fail\n        if ok:\n            break\n"
                "        waited += min(CAP_MS, BASE_MS * 2 ** attempt)\n        attempt += 1\nprint(waited)")


class TokenBucket(_Exec):
    """b = 0.7 (middle): tokens refill continuously at `rate` per second up to `capacity`; a
    request spends one token or is rejected. Bursts drain the bucket; gaps refill it."""
    meta = _meta("be.http.token_bucket.v1", "backend.http", 0.7, t=240)
    SEMANTIC = ("capacity", "rate", "times")
    STEM = "Ограничитель частоты запросов (token bucket) на API-шлюзе. Время запросов — в секундах."

    def draw(self, rng):
        while True:
            times = sorted(rng.sample(range(0, 30), rng.randint(8, 13)))
            p = {"capacity": rng.randint(2, 4), "rate": rng.choice((0.25, 0.5, 1.0)), "times": times}
            if 0 < self.solve(p) < sum(times):          # something is rejected
                return p

    def solve(self, p):
        tokens, last, total = float(p["capacity"]), 0, 0
        for t in p["times"]:
            tokens = min(p["capacity"], tokens + (t - last) * p["rate"])
            last = t
            if tokens >= 1:
                tokens -= 1
                total += t
        return total

    def program(self, p):
        return (f"CAPACITY, RATE = {p['capacity']}, {p['rate']}\n"
                "tokens, last = float(CAPACITY), 0\naccepted_sum = 0\n"
                f"for t in {p['times']}:\n    tokens = min(CAPACITY, tokens + (t - last) * RATE)\n    last = t\n"
                "    if tokens >= 1:\n        tokens -= 1\n        accepted_sum += t\nprint(accepted_sum)")


class Lockout(_Exec):
    """b = 0.3 (middle): `limit` consecutive failures lock the account for `lock_s` seconds;
    attempts during the lock are rejected without checking the password and do not extend it;
    a success resets the failure counter."""
    meta = _meta("be.sec.lockout.v1", "backend.security", 0.3, t=240, skills=("security",))
    SEMANTIC = ("limit", "lock_s", "events")
    STEM = "Защита входа от перебора паролей: блокировка после нескольких неудачных попыток подряд."

    def draw(self, rng):
        while True:
            times = sorted(rng.sample(range(0, 120), rng.randint(9, 14)))
            events = [[t, rng.random() < 0.3] for t in times]
            p = {"limit": rng.randint(2, 3), "lock_s": rng.choice((10, 20, 30, 45)), "events": events}
            if self.solve(p) > 0:
                return p

    def solve(self, p):
        fails, locked_until, rejected = 0, -1, 0
        for t, ok in p["events"]:
            if t < locked_until:
                rejected += t
                continue
            if ok:
                fails = 0
            else:
                fails += 1
                if fails >= p["limit"]:
                    locked_until, fails = t + p["lock_s"], 0
        return rejected

    def program(self, p):
        events = ", ".join(f"({t}, {ok})" for t, ok in p["events"])
        return (f"LIMIT, LOCK_S = {p['limit']}, {p['lock_s']}\nevents = [{events}]  # (время, пароль верный)\n\n"
                "fails, locked_until, rejected = 0, -1, 0\nfor t, ok in events:\n    if t < locked_until:\n"
                "        rejected += t\n        continue\n    if ok:\n        fails = 0\n    else:\n        fails += 1\n"
                "        if fails >= LIMIT:\n            locked_until, fails = t + LOCK_S, 0\nprint(rejected)")


class TokenExpiry(_Exec):
    """b = -0.1 (upper junior): a token is valid when nbf - leeway <= now < exp + leeway; the
    leeway widens both ends, and `exp` itself is already expired without it."""
    meta = _meta("be.sec.token_expiry.v1", "backend.security", -0.1, a=1.1, t=180, skills=("security",))
    SEMANTIC = ("tokens", "now", "leeway")
    STEM = "Сервис проверяет срок действия токенов с допуском на расхождение часов (leeway)."

    def draw(self, rng):
        while True:
            now, leeway = rng.randint(1000, 1100), rng.choice((0, 5, 10, 30))
            ids = rng.sample(range(1, 100), rng.randint(5, 8))
            tokens = []
            for tid in ids:
                nbf = now + rng.randint(-60, 20)
                tokens.append([tid, nbf, nbf + rng.randint(10, 90)])
            p = {"tokens": tokens, "now": now, "leeway": leeway}
            if 0 < self.solve(p) < sum(ids):
                return p

    def solve(self, p):
        lw, now = p["leeway"], p["now"]
        return sum(tid for tid, nbf, exp in p["tokens"] if nbf - lw <= now < exp + lw)

    def program(self, p):
        rows = ",\n    ".join(f'{{"id": {t}, "nbf": {n}, "exp": {e}}}' for t, n, e in p["tokens"])
        return (f"NOW, LEEWAY = {p['now']}, {p['leeway']}\ntokens = [\n    {rows},\n]\n\n"
                "def valid(tok):\n    return tok[\"nbf\"] - LEEWAY <= NOW < tok[\"exp\"] + LEEWAY\n\n"
                "print(sum(tok[\"id\"] for tok in tokens if valid(tok)))")


FAMILIES = [RetryBackoff(), TokenBucket(), Lockout(), TokenExpiry()]
