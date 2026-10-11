"""Shared code-reading and data-structure families added in ML-13. Typed answers, exec oracles.

sh.code.prefix_sums.v1     a slice sum read off a prefix-sum array
sh.code.word_lengths.v1    total length of the words longer than k
sh.code.collatz_steps.v1   total Collatz steps over a few start values
sh.code.gcd_trace.v1       sum of the remainders Euclid's algorithm produces
sh.code.recurrence.v1      a linear recurrence with drawn coefficients and seeds
sh.ds.counter_squares.v1   Σ count² over a word Counter
sh.ds.bubble_moved.v1      sum of the larger values bubble sort moves right
sh.ds.linear_probing.v1    Σ slot·key after open addressing with linear probing
sh.ds.bst_depth.v1         Σ depth·key after inserting keys into an unbalanced BST
sh.ds.bfs_distance.v1      Σ vertex·distance of a BFS on a small directed graph
sh.ds.lru_evicted.v1       sum of the keys an LRU cache evicts

Same contract as code_trace.py: `solve` computes the answer from the drawn parameters in plain
Python; the oracle executes the program the candidate sees. Every answer is a weighted sum or a
count over a wide range, so no single typed number is right on many items (harness modal gate).
"""
from __future__ import annotations

from ..base import FamilyMeta
from ..builder import TypedNumberFamily, run_python

ALL = ("backend", "frontend", "ml_data")
WORDS = ("api", "cache", "queue", "log", "token", "index", "shard", "event", "batch", "node", "graph", "key")
LONG_WORDS = ("db", "io", "api", "log", "tree", "heap", "cache", "queue", "router", "socket", "handler",
              "pipeline", "scheduler", "transaction", "serializer", "middleware")


def _meta(fid, topic, b, a=1.1, t=150):
    return FamilyMeta(id=fid, version=1, specs=ALL, topic=topic, skills=("algorithms",),
                      format="code_output", a=a, b=b, c=0.0, time_limit_s=t)


class _Exec(TypedNumberFamily):
    def oracle_value(self, inst):
        return float(run_python(inst.code["text"]))

    def render(self, p):
        return "Что напечатает программа?", {"lang": "python", "text": self.program(p)}

    def program(self, p) -> str:
        raise NotImplementedError


class PrefixSums(_Exec):
    """b = -0.4 (junior): pre[k] is the sum of the first k values, so pre[j] - pre[i] is
    xs[i:j]; the off-by-one (xs[i..j] inclusive) gives a different number."""
    meta = _meta("sh.code.prefix_sums.v1", "algorithms.code_reading", -0.4, t=120)
    SEMANTIC = ("xs", "i", "j")

    def draw(self, rng):
        xs = [rng.randint(1, 60) for _ in range(rng.randint(8, 13))]
        i = rng.randint(1, len(xs) - 4)
        return {"xs": xs, "i": i, "j": rng.randint(i + 2, len(xs) - 1)}

    def solve(self, p):
        return sum(p["xs"][p["i"]:p["j"]])

    def program(self, p):
        return (f"xs = {p['xs']}\npre = [0]\nfor x in xs:\n    pre.append(pre[-1] + x)\n"
                f"print(pre[{p['j']}] - pre[{p['i']}])")


class WordLengths(_Exec):
    """b = -0.8 (junior): split, filter by length, sum lengths."""
    meta = _meta("sh.code.word_lengths.v1", "algorithms.code_reading", -0.8, a=1.0, t=90)
    SEMANTIC = ("words", "k")

    def draw(self, rng):
        while True:
            words = [rng.choice(LONG_WORDS) for _ in range(rng.randint(7, 14))]
            k = rng.randint(3, 7)
            p = {"words": words, "k": k}
            if 0 < self.solve(p) < sum(map(len, words)):
                return p

    def solve(self, p):
        return sum(len(w) for w in p["words"] if len(w) > p["k"])

    def program(self, p):
        text = " ".join(p["words"])
        return f'text = "{text}"\nprint(sum(len(w) for w in text.split() if len(w) > {p["k"]}))'


def _collatz(n):
    steps = 0
    while n != 1:
        n = n // 2 if n % 2 == 0 else 3 * n + 1
        steps += 1
    return steps


class CollatzSteps(_Exec):
    """b = -0.2 (upper junior): a while loop with two branches, run for 2-3 start values."""
    meta = _meta("sh.code.collatz_steps.v1", "algorithms.code_reading", -0.2, t=180)
    SEMANTIC = ("starts",)

    def draw(self, rng):
        return {"starts": sorted(rng.sample(range(3, 300), rng.randint(3, 4)))}

    def solve(self, p):
        return sum(_collatz(n) for n in p["starts"])

    def program(self, p):
        return ("def steps(n):\n    s = 0\n    while n != 1:\n        n = n // 2 if n % 2 == 0 else 3 * n + 1\n"
                f"        s += 1\n    return s\n\n\nprint(sum(steps(n) for n in {p['starts']}))")


class GcdTrace(_Exec):
    """b = 0.0 (junior/middle cut): Euclid's loop; the printed value is the sum of every
    remainder computed (the last one is 0), so the trace has to be followed step by step."""
    meta = _meta("sh.code.gcd_trace.v1", "algorithms.code_reading", 0.0)
    SEMANTIC = ("a", "b")

    def draw(self, rng):
        while True:
            a, b = rng.randint(100, 5000), rng.randint(20, 2000)
            if a > b and a % b and self.solve({"a": a, "b": b}) > b:
                return {"a": a, "b": b}

    def solve(self, p):
        a, b, total = p["a"], p["b"], 0
        while b:
            a, b = b, a % b
            total += b
        return total

    def program(self, p):
        return (f"a, b = {p['a']}, {p['b']}\ntotal = 0\nwhile b:\n    a, b = b, a % b\n    total += b\n"
                "print(total)")


class Recurrence(_Exec):
    """b = 0.2 (middle): f(n) = p·f(n-1) + q·f(n-2) + c unrolled by a loop with tuple assignment
    (the right-hand side is evaluated before either name is rebound)."""
    meta = _meta("sh.code.recurrence.v1", "algorithms.code_reading", 0.2)
    SEMANTIC = ("f0", "f1", "p", "q", "c", "n")

    def draw(self, rng):
        return {"f0": rng.randint(0, 40), "f1": rng.randint(1, 40), "p": rng.randint(1, 3), "q": rng.randint(1, 3),
                "c": rng.randint(0, 20), "n": rng.randint(4, 7)}

    def solve(self, p):
        a, b = p["f0"], p["f1"]
        for _ in range(p["n"] - 1):
            a, b = b, p["p"] * b + p["q"] * a + p["c"]
        return b

    def program(self, p):
        return (f"a, b = {p['f0']}, {p['f1']}\nfor _ in range({p['n'] - 1}):\n    a, b = b, {p['p']} * b + {p['q']} * a + {p['c']}\n"
                "print(b)")


class CounterSquares(_Exec):
    """b = -0.5 (junior): counting with a dict and .get; Σ count² rewards exact counts."""
    meta = _meta("sh.ds.counter_squares.v1", "algorithms.data_structures", -0.5, a=1.0, t=120)
    SEMANTIC = ("words",)

    def draw(self, rng):
        vocab = rng.sample(WORDS, rng.randint(3, 5))
        return {"words": [rng.choice(vocab) for _ in range(rng.randint(8, 14))]}

    def solve(self, p):
        return sum(p["words"].count(w) ** 2 for w in sorted(set(p["words"])))

    def program(self, p):
        return (f"words = {p['words']}\ncounts = {{}}\nfor w in words:\n    counts[w] = counts.get(w, 0) + 1\n"
                "print(sum(v * v for v in counts.values()))")


class BubbleMoved(_Exec):
    """b = 0.4 (middle): every swap moves the larger of two neighbours right; the printed value
    adds that larger value, so each swap has to be found (a weighted inversion count)."""
    meta = _meta("sh.ds.bubble_moved.v1", "algorithms.data_structures", 0.4, t=240)
    SEMANTIC = ("xs",)

    def draw(self, rng):
        while True:
            xs = rng.sample(range(1, 40), rng.randint(5, 7))
            if 0 < self.solve({"xs": xs}):
                return {"xs": xs}

    def solve(self, p):
        return sum(p["xs"][i] for i in range(len(p["xs"])) for j in range(i + 1, len(p["xs"]))
                   if p["xs"][i] > p["xs"][j])

    def program(self, p):
        return (f"xs = {p['xs']}\nmoved = 0\nfor end in range(len(xs) - 1, 0, -1):\n    for i in range(end):\n"
                "        if xs[i] > xs[i + 1]:\n            moved += xs[i]\n            xs[i], xs[i + 1] = xs[i + 1], xs[i]\n"
                "print(moved)")


class LinearProbing(_Exec):
    """b = 0.6 (middle): open addressing, h(k) = k mod m, linear probing; colliding keys slide
    to the next free slot, so the weighted sum depends on the insertion order."""
    meta = _meta("sh.ds.linear_probing.v1", "algorithms.data_structures", 0.6, a=1.2, t=240)
    SEMANTIC = ("m", "keys")

    def draw(self, rng):
        while True:
            m = rng.choice((7, 11, 13))
            keys = rng.sample(range(10, 100), rng.randint(5, m - 2))
            p = {"m": m, "keys": keys}
            naive = sum((k % m) * k for k in keys)
            if self.solve(p) != naive:                  # at least one collision moves a key
                return p

    def solve(self, p):
        table = [None] * p["m"]
        for k in p["keys"]:
            i = k % p["m"]
            while table[i] is not None:
                i = (i + 1) % p["m"]
            table[i] = k
        return sum(i * k for i, k in enumerate(table) if k is not None)

    def program(self, p):
        return (f"m = {p['m']}\ntable = [None] * m\nfor k in {p['keys']}:\n    i = k % m\n"
                "    while table[i] is not None:\n        i = (i + 1) % m\n    table[i] = k\n"
                "print(sum(i * k for i, k in enumerate(table) if k is not None))")


class BstDepth(_Exec):
    """b = 0.5 (middle): an unbalanced BST's shape follows the insertion order."""
    meta = _meta("sh.ds.bst_depth.v1", "algorithms.data_structures", 0.5, t=240)
    SEMANTIC = ("keys",)

    def draw(self, rng):
        return {"keys": rng.sample(range(1, 60), rng.randint(6, 9))}

    def solve(self, p):
        nodes: dict[int, tuple[int, int | None, int | None]] = {}
        root = None
        total = 0
        for k in p["keys"]:
            depth, cur = 0, root
            parent, side = None, None
            while cur is not None:
                parent, side = cur, ("l" if k < cur else "r")
                cur = nodes[cur][1] if k < cur else nodes[cur][2]
                depth += 1
            nodes[k] = (depth, None, None)
            if parent is None:
                root = k
            else:
                d, left, right = nodes[parent]
                nodes[parent] = (d, k, right) if side == "l" else (d, left, k)
            total += depth * k
        return total

    def program(self, p):
        return (f"tree = {{}}\nroot = None\ntotal = 0\nfor k in {p['keys']}:\n    depth, cur = 0, root\n"
                "    while cur is not None:\n        left, right = tree[cur]\n        nxt = left if k < cur else right\n"
                "        if nxt is None:\n            tree[cur] = (k, right) if k < cur else (left, k)\n"
                "            depth += 1\n            break\n        cur = nxt\n        depth += 1\n"
                "    if root is None:\n        root = k\n    tree[k] = (None, None)\n    total += depth * k\nprint(total)")


class BfsDistance(_Exec):
    """b = 0.7 (middle): BFS distances on a directed graph; unreachable vertices add nothing."""
    meta = _meta("sh.ds.bfs_distance.v1", "algorithms.data_structures", 0.7, a=1.2, t=240)
    SEMANTIC = ("adj",)

    def draw(self, rng):
        while True:
            n = rng.randint(6, 8)
            adj = {v: sorted(rng.sample([u for u in range(n) if u != v], rng.randint(0, 2))) for v in range(n)}
            p = {"adj": adj}
            if self.solve(p) >= 10:
                return p

    def solve(self, p):
        dist = {0: 0}
        queue = [0]
        while queue:
            v = queue.pop(0)
            for u in p["adj"][v]:
                if u not in dist:
                    dist[u] = dist[v] + 1
                    queue.append(u)
        return sum(v * d for v, d in dist.items())

    def program(self, p):
        return (f"from collections import deque\n\ngraph = {p['adj']}\ndist = {{0: 0}}\nqueue = deque([0])\n"
                "while queue:\n    v = queue.popleft()\n    for u in graph[v]:\n        if u not in dist:\n"
                "            dist[u] = dist[v] + 1\n            queue.append(u)\nprint(sum(v * d for v, d in dist.items()))")


class LruEvicted(_Exec):
    """b = 0.8 (upper middle): an OrderedDict LRU; a hit moves the key to the end, so the
    evicted key is the least recently used, not the oldest inserted (FIFO gives a different sum)."""
    meta = _meta("sh.ds.lru_evicted.v1", "algorithms.data_structures", 0.8, a=1.2, t=240)
    SEMANTIC = ("cap", "seq")

    def draw(self, rng):
        while True:
            cap = rng.randint(2, 4)
            seq = [rng.randint(1, 9) for _ in range(rng.randint(9, 14))]
            p = {"cap": cap, "seq": seq}
            if self.solve(p) > 0 and self.solve(p) != self._fifo(p):
                return p

    @staticmethod
    def _fifo(p):
        cache: list[int] = []
        out = 0
        for k in p["seq"]:
            if k not in cache:
                if len(cache) == p["cap"]:
                    out += cache.pop(0)
                cache.append(k)
        return out

    def solve(self, p):
        cache: list[int] = []
        out = 0
        for k in p["seq"]:
            if k in cache:
                cache.remove(k)
            elif len(cache) == p["cap"]:
                out += cache.pop(0)
            cache.append(k)
        return out

    def program(self, p):
        return (f"from collections import OrderedDict\n\ncache = OrderedDict()\nevicted = 0\nfor k in {p['seq']}:\n"
                "    if k in cache:\n        cache.move_to_end(k)\n        continue\n"
                f"    if len(cache) == {p['cap']}:\n        old, _ = cache.popitem(last=False)\n        evicted += old\n"
                "    cache[k] = True\nprint(evicted)")


FAMILIES = [PrefixSums(), WordLengths(), CollatzSteps(), GcdTrace(), Recurrence(),
            CounterSquares(), BubbleMoved(), LinearProbing(), BstDepth(), BfsDistance(), LruEvicted()]
