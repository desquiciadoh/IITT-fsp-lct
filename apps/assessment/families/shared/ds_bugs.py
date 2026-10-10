"""Shared data-structure and debugging families.

sh.ds.heap_order.v1     order of values popped from a heapq min-heap (choice, redraw distractors)
sh.ds.op_cost.v1        cost of one operation on a Python structure (classification, 4 classes)
sh.code.find_bug.v1     which line breaks a 5-line function (find_bug, 5 fixed line options)
"""
from __future__ import annotations

import re

from ..base import FamilyMeta, Instance
from ..builder import ClassificationFamily, RedrawChoiceFamily, run_python

ALL_SPECS = ("backend", "frontend", "ml_data")


class HeapOrder(RedrawChoiceFamily):
    """b = 0.2 (lower middle): heapq is a min-heap and pops the smallest present value, not the
    oldest or the last pushed; interleaved pushes and pops make that visible."""

    meta = FamilyMeta(id="sh.ds.heap_order.v1", version=1, specs=ALL_SPECS,
                      topic="algorithms.data_structures", skills=("data_structures", "python"),
                      format="code_output", a=1.2, b=0.2, c=0.25, time_limit_s=120)

    def draw(self, rng):
        values = rng.sample(range(1, 60), 8)
        ops, size, pops, vi = [], 0, 0, 0
        while pops < 4:
            if size and (vi >= len(values) or rng.random() < 0.4):
                ops.append(["pop"])
                size -= 1
                pops += 1
            else:
                ops.append(["push", values[vi]])
                vi += 1
                size += 1
        return {"ops": ops, "name": rng.choice(("heap", "pq", "h", "queue", "tasks"))}

    def answer(self, p):
        import heapq

        heap, out = [], []
        for op in p["ops"]:
            if op[0] == "push":
                heapq.heappush(heap, op[1])
            else:
                out.append(heapq.heappop(heap))
        return str(out)

    def misconceptions(self, p):
        stack, queue, out_s, out_q = [], [], [], []
        for op in p["ops"]:
            if op[0] == "push":
                stack.append(op[1])
                queue.append(op[1])
            else:
                out_s.append(stack.pop())
                out_q.append(queue.pop(0))
        return [str(out_s), str(out_q)]                   # treated as a stack / as a FIFO queue

    def render(self, p):
        name = p["name"]
        lines = ["import heapq", "", f"{name} = []", "out = []"]
        for op in p["ops"]:
            if op[0] == "push":
                lines.append(f"heapq.heappush({name}, {op[1]})")
            else:
                lines.append(f"out.append(heapq.heappop({name}))")
        lines.append("print(out)")
        return "Что напечатает программа?", {"lang": "python", "text": "\n".join(lines)}

    def oracle_answer(self, inst):
        return run_python(inst.code["text"])


# ── operation cost (classification) ────────────────────────────────────────

COST_LABELS = ("Θ(1)", "Θ(log n)", "Θ(n)", "Θ(n log n)")
# (structure, operation) per class. Average/amortized costs of CPython's built-ins.
OPERATIONS = {
    "Θ(1)": [("список", "{v}.append(x)"), ("список", "{v}.pop()"), ("словарь", "{v}[key] = x"),
             ("словарь", "x = {v}[key]"), ("множество", "x in {v}"), ("список", "len({v})"),
             ("deque", "{v}.appendleft(x)"), ("deque", "{v}.popleft()")],
    "Θ(log n)": [("куча (heapq)", "heapq.heappush({v}, x)"), ("куча (heapq)", "heapq.heappop({v})"),
                 ("отсортированный список", "bisect.bisect_left({v}, x)")],
    "Θ(n)": [("список", "{v}.insert(0, x)"), ("список", "x in {v}"), ("список", "{v}.pop(0)"),
             ("список", "min({v})"), ("список", "{v}.remove(x)"), ("список", "heapq.heapify({v})"),
             ("список", "{v}.index(x)")],
    "Θ(n log n)": [("список", "sorted({v})"), ("список", "{v}.sort()")],
}
# Independent lookup on the rendered operation (method or function name), reviewed by hand.
ORACLE_TABLE = {
    ".append(": "Θ(1)", ".pop()": "Θ(1)", "] = x": "Θ(1)", "x = ": "Θ(1)", "len(": "Θ(1)",
    ".appendleft(": "Θ(1)", ".popleft(": "Θ(1)", "heappush": "Θ(log n)", "heappop": "Θ(log n)",
    "bisect_left": "Θ(log n)", ".insert(0": "Θ(n)", ".pop(0)": "Θ(n)", "min(": "Θ(n)", ".remove(": "Θ(n)",
    "heapify": "Θ(n)", ".index(": "Θ(n)", "sorted(": "Θ(n log n)", ".sort()": "Θ(n log n)",
}
CONTEXTS = ("заказов", "пользователей", "событий", "логов", "товаров", "задач", "сообщений", "платежей",
            "сессий", "отзывов")


class OperationCost(ClassificationFamily):
    """b = -0.3 (upper junior): append vs insert(0), list vs set membership, heapify being linear,
    sort being n log n: the standard costs every developer is expected to know."""

    meta = FamilyMeta(id="sh.ds.op_cost.v1", version=1, specs=ALL_SPECS,
                      topic="algorithms.data_structures", skills=("data_structures", "algorithms"),
                      format="concept_mcq", a=1.0, b=-0.3, c=0.25, time_limit_s=60)
    LABELS = COST_LABELS

    def draw(self, rng, label):
        kind, op = OPERATIONS[label][rng.randrange(len(OPERATIONS[label]))]
        return {"kind": kind, "op": op, "n": rng.randint(10, 9999) * 1000,
                "var": rng.choice(("items", "data", "store", "pool", "cache", "rows", "q", "bag")),
                "ctx": rng.choice(CONTEXTS)}

    def render(self, p):
        line = p["op"].format(v=p["var"])
        n = f"{p['n']:,}".replace(",", " ")
        stem = (f"`{p['var']}` — {p['kind']} из n = {n} {p['ctx']}. Какова средняя (амортизированная) "
                "сложность одной операции ниже как функция от n?")
        return stem, {"lang": "python", "text": line}

    def classify(self, inst: Instance):
        text = inst.code["text"]
        if "x in " in text:
            return "Θ(1)" if "множество" in inst.stem_md else "Θ(n)"
        hits = {label for marker, label in ORACLE_TABLE.items() if marker in text}
        return hits.pop() if len(hits) == 1 else None


# ── find the bug ───────────────────────────────────────────────────────────

# Each task: a spec sentence, five body lines (lines 2..6 of the listing) and one buggy variant
# per line. Placeholders: {k} constant, {acc} accumulator, {it} loop variable, {arg} parameter.
# `_spec_value` is an independent implementation of the spec sentence.
TASKS = {
    "sum_div": {
        "spec": "возвращает сумму всех чисел от 1 до {arg} включительно, которые делятся на {k}",
        "body": ["    {acc} = 0", "    for {it} in range(1, {arg} + 1):", "        if {it} % {k} == 0:",
                 "            {acc} += {it}", "    return {acc}"],
        "bugs": ["    {acc} = 1", "    for {it} in range(1, {arg}):", "        if {it} % {k} != 0:",
                 "            {acc} += 1", "    return {it}"],
        "kind": "num", "k": (2, 13),
    },
    "count_gt": {
        "spec": "возвращает, сколько элементов списка {arg} строго больше {k}",
        "body": ["    {acc} = 0", "    for {it} in {arg}:", "        if {it} > {k}:", "            {acc} += 1",
                 "    return {acc}"],
        "bugs": ["    {acc} = 1", "    for {it} in {arg}[1:]:", "        if {it} >= {k}:",
                 "            {acc} += {it}", "    return {it}"],
        "kind": "list", "k": (1, 99),
    },
    "max_mul": {
        "spec": "возвращает максимальный элемент непустого списка {arg} (числа могут быть отрицательными), "
                "умноженный на {k}",
        "body": ["    {acc} = {arg}[0]", "    for {it} in {arg}:", "        if {it} > {acc}:",
                 "            {acc} = {it}", "    return {acc} * {k}"],
        "bugs": ["    {acc} = 0", "    for {it} in {arg}[:-1]:", "        if {it} < {acc}:",
                 "            {it} = {acc}", "    return {arg}[-1] * {k}"],
        "kind": "list", "k": (2, 25),
    },
    "prod_skip": {
        "spec": "возвращает произведение всех чисел от 2 до {arg} включительно, которые НЕ делятся на {k}",
        "body": ["    {acc} = 1", "    for {it} in range(2, {arg} + 1):", "        if {it} % {k} != 0:",
                 "            {acc} *= {it}", "    return {acc}"],
        "bugs": ["    {acc} = 0", "    for {it} in range(2, {arg}):", "        if {it} % {k} == 0:",
                 "            {acc} += {it}", "    return {it}"],
        "kind": "num", "k": (2, 9),
    },
}
NAMES = {
    "num": {"arg": ("n", "m", "limit", "top", "upto"), "it": ("i", "j", "t", "num", "v")},
    "list": {"arg": ("a", "arr", "nums", "values", "xs"), "it": ("x", "v", "item", "e", "el")},
}
ACCS = ("total", "s", "acc", "res", "out", "best_", "r", "value", "answer", "agg")
FNS = ("solve", "compute", "f", "run", "calc", "check", "go", "evaluate", "process", "measure", "score", "fold")


def _spec_value(task: str, k: int, arg):
    """Independent reference implementation of each spec sentence."""
    if task == "sum_div":
        return sum(i for i in range(1, arg + 1) if i % k == 0)
    if task == "count_gt":
        return len([x for x in arg if x > k])
    if task == "max_mul":
        return max(arg) * k
    out = 1
    for i in range(2, arg + 1):
        if i % k:
            out *= i
    return out


def _probe_args(task: str, k: int):
    """Inputs on which every listed bug changes the output (checked per item by _repairs)."""
    if TASKS[task]["kind"] == "num":
        return [2, 5, 9, 12, 14, 20, 21]
    if task == "count_gt":
        return [[k, k + 1, k + 7, 0, k], [k + 2, -1], [k]]
    return [[-k, -1, -(k + 3)], [k, k + 9, -(k + 1), 1], [-(k + 2), 3, -(k + 8), k + 1]]


def _names(lines: list[str]) -> dict[str, str]:
    """Recover the names the listing uses (four of five body lines are correct)."""
    return {"fn": lines[0].split()[1].split("(")[0],
            "arg": re.findall(r"\((\w+)", lines[0])[0],
            "acc": re.findall(r"^\s+(\w+) = ", lines[1])[0],
            "it": re.findall(r"for (\w+) in", lines[2])[0]}


def _repairs(lines: list[str], task: str, k: int) -> list[int]:
    """Indices i (0..4) such that restoring body line i makes the function meet the spec."""
    names = _names(lines)
    reference = [ln.format(k=k, **names) for ln in TASKS[task]["body"]]
    args = _probe_args(task, k)
    want = [str(_spec_value(task, k, a)) for a in args]
    calls = "\n".join(f"print({names['fn']}({a!r}))" for a in args)
    fixes = []
    for i in range(5):
        trial = list(lines[:6])
        trial[i + 1] = reference[i]
        try:
            got = run_python("\n".join(trial) + "\n" + calls).split("\n")
        except Exception:          # a repair that still crashes is not a repair
            continue
        if got == want:
            fixes.append(i)
    return fixes


def _k_from(stem: str) -> int:
    return int(re.findall(r"(?:на|больше) (-?\d+)", stem)[-1])


class FindBug(ClassificationFamily):
    """b = -0.5 (junior): the spec is one sentence and the function five lines; the bugs are the
    everyday ones (wrong initial value, off-by-one range, inverted condition, wrong update,
    wrong return). The answer line is uniform over the five lines, the options are fixed."""

    meta = FamilyMeta(id="sh.code.find_bug.v1", version=1, specs=ALL_SPECS,
                      topic="algorithms.code_reading", skills=("algorithms", "python"),
                      format="find_bug", a=1.1, b=-0.5, c=0.2, time_limit_s=120)
    LABELS = ("Строка 2", "Строка 3", "Строка 4", "Строка 5", "Строка 6")

    def draw(self, rng, label):
        while True:
            task = sorted(TASKS)[rng.randrange(len(TASKS))]
            t = TASKS[task]
            pools = NAMES[t["kind"]]
            p = {"task": task, "k": rng.randint(*t["k"]), "bug": self.LABELS.index(label),
                 "fn": rng.choice(FNS), "acc": rng.choice(ACCS), "it": rng.choice(pools["it"]),
                 "arg": rng.choice(pools["arg"]), "hint": rng.random() < 0.5}
            if p["acc"] in (p["it"], p["arg"]):
                continue
            if _repairs(self._lines(p), task, p["k"]) == [p["bug"]]:
                return p

    def _lines(self, p):
        t = TASKS[p["task"]]
        names = {"acc": p["acc"], "it": p["it"], "arg": p["arg"], "k": p["k"]}
        body = [ln.format(**names) for ln in t["body"]]
        body[p["bug"]] = t["bugs"][p["bug"]].format(**names)
        hint = (": int" if t["kind"] == "num" else ": list[int]") if p["hint"] else ""
        ret = " -> int" if p["hint"] else ""
        return [f"def {p['fn']}({p['arg']}{hint}){ret}:", *body]

    def render(self, p):
        spec = TASKS[p["task"]]["spec"].format(k=p["k"], arg=p["arg"])
        return (f"Функция `{p['fn']}` {spec}. Ровно в одной строке листинга ошибка (строка 1 — `def`). "
                "В какой строке?", {"lang": "python", "text": "\n".join(self._lines(p))})

    def classify(self, inst: Instance):
        """Line-repair oracle: restore each line of the reference in turn; exactly one repair must
        make the function agree with the independent spec implementation on all probes."""
        lines = inst.code["text"].split("\n")
        task = next(t for t, v in TASKS.items() if v["spec"].split("{")[0] in inst.stem_md)
        fixes = _repairs(lines, task, _k_from(inst.stem_md))
        return self.LABELS[fixes[0]] if len(fixes) == 1 else None


FAMILIES = [HeapOrder(), OperationCost(), FindBug()]
