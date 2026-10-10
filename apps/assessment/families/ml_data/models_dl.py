"""ML & Data families on models, data processing and deep learning.

ml.models.knn.v1             k-NN regression prediction (typed; oracle re-sorts by squared distance)
ml.models.gini.v1            Gini impurity / weighted Gini after a split (typed; Fraction oracle)
ml.models.fit_diagnosis.v1   overfitting / underfitting / fine from train and validation scores (classification)
ml.data.groupby.v1           pandas groupby aggregate with missing values (typed; sqlite oracle)
ml.data.broadcast.v1         numpy broadcasting result shape or error (choice; numpy oracle)
ml.dl.conv_output.v1         Conv2d output size (typed; sliding-window count oracle)
ml.dl.param_count.v1         trainable parameters of a small network (typed; numpy-array oracle)
"""
from __future__ import annotations

import re
import sqlite3
from fractions import Fraction

from ..base import FamilyMeta, Instance
from ..builder import ClassificationFamily, RedrawChoiceFamily, TypedNumberFamily

M = ("ml_data",)


class Knn(TypedNumberFamily):
    """b = -0.3 (upper junior): find the k nearest points by Euclidean distance and average their
    targets; using k = 1 or the wrong metric gives a different answer."""

    meta = FamilyMeta(id="ml.models.knn.v1", version=1, specs=M, topic="ml.models",
                      skills=("machine_learning", "scikit_learn"), format="numeric_scenario", a=1.1, b=-0.3,
                      c=0.0, time_limit_s=150)
    DECIMALS = 2

    def draw(self, rng):
        while True:
            points = [[rng.randint(0, 10), rng.randint(0, 10), rng.randint(10, 99)] for _ in range(rng.randint(5, 7))]
            q = [rng.randint(0, 10), rng.randint(0, 10)]
            k = rng.randint(2, 3)
            d = sorted((x - q[0]) ** 2 + (y - q[1]) ** 2 for x, y, _ in points)
            coords = {(x, y) for x, y, _ in points}
            if len(coords) == len(points) and d[k - 1] != d[k]:          # no tie at the k-th neighbour
                return {"points": points, "q": q, "k": k}

    def solve(self, p):
        q = p["q"]
        nearest = sorted(p["points"], key=lambda t: ((t[0] - q[0]) ** 2 + (t[1] - q[1]) ** 2) ** 0.5)[: p["k"]]
        return sum(t[2] for t in nearest) / p["k"]

    def render(self, p):
        rows = "\n".join(f"({x}, {y}) -> {t}" for x, y, t in p["points"])
        return (f"Обучающая выборка для регрессии (признаки x1, x2 -> целевое значение):\n\n{rows}\n\n"
                f"Каким будет прогноз k-NN с k = {p['k']} (евклидово расстояние, среднее значение соседей) "
                f"для точки ({p['q'][0]}, {p['q'][1]})?", None)

    def oracle_value(self, inst):
        pts = [tuple(int(v) for v in m) for m in re.findall(r"\((\d+), (\d+)\) -> (\d+)", inst.stem_md)]
        k = int(re.search(r"k = (\d+)", inst.stem_md).group(1))
        qx, qy = (int(v) for v in re.search(r"для точки \((\d+), (\d+)\)", inst.stem_md).groups())
        by_distance = sorted(pts, key=lambda t: (t[0] - qx) ** 2 + (t[1] - qy) ** 2)
        return float(Fraction(sum(t[2] for t in by_distance[:k]), k))


class Gini(TypedNumberFamily):
    """b = 0.5 (middle): Gini = 1 − Σ p_i²; after a split, the children's impurities are weighted
    by their sizes. Forgetting the weights is the usual error."""

    meta = FamilyMeta(id="ml.models.gini.v1", version=1, specs=M, topic="ml.models",
                      skills=("machine_learning",), format="numeric_scenario", a=1.2, b=0.5, c=0.0,
                      time_limit_s=150)
    DECIMALS = 3

    def draw(self, rng):
        left = [rng.randint(0, 12) for _ in range(2)]
        right = [rng.randint(0, 12) for _ in range(2)]
        if sum(left) == 0:
            left[0] = 1
        if sum(right) == 0:
            right[1] = 1
        return {"left": left, "right": right, "ask": rng.choice(("parent", "split", "gain")),
                "classes": rng.choice((("да", "нет"), ("спам", "не спам"), ("уйдёт", "останется"),
                                       ("купит", "не купит")))}

    @staticmethod
    def _gini(counts):
        n = sum(counts)
        return 1 - sum((c / n) ** 2 for c in counts)

    def solve(self, p):
        parent = [a + b for a, b in zip(p["left"], p["right"], strict=True)]
        n = sum(parent)
        split = sum(sum(p[side]) / n * self._gini(p[side]) for side in ("left", "right"))
        return {"parent": self._gini(parent), "split": split, "gain": self._gini(parent) - split}[p["ask"]]

    def render(self, p):
        a, b = p["classes"]
        L, R = p["left"], p["right"]
        ask = {"parent": "индекс Джини родительского узла",
               "split": "взвешенный индекс Джини после разбиения",
               "gain": "уменьшение индекса Джини (родитель минус взвешенная сумма детей)"}[p["ask"]]
        return (f"Узел дерева разбит на два. Левый потомок: «{a}» — {L[0]}, «{b}» — {L[1]}. Правый потомок: "
                f"«{a}» — {R[0]}, «{b}» — {R[1]}. Найдите {ask}.", None)

    def oracle_value(self, inst):
        nums = [int(x) for x in re.findall(r"— (\d+)", inst.stem_md)]
        left, right = nums[:2], nums[2:4]

        def gini(c):
            n = sum(c)
            return 1 - sum(Fraction(x, n) ** 2 for x in c)
        parent = [left[0] + right[0], left[1] + right[1]]
        n = sum(parent)
        split = Fraction(sum(left), n) * gini(left) + Fraction(sum(right), n) * gini(right)
        if "родительского" in inst.stem_md:
            return float(gini(parent))
        if "уменьшение" in inst.stem_md:
            return float(gini(parent) - split)
        return float(split)


class FitDiagnosis(ClassificationFamily):
    """b = -0.8 (junior): a big train/validation gap is overfitting, both scores low is
    underfitting, both high and close is a healthy fit."""

    meta = FamilyMeta(id="ml.models.fit_diagnosis.v1", version=1, specs=M, topic="ml.models",
                      skills=("machine_learning",), format="concept_mcq", a=1.0, b=-0.8, c=1 / 3, time_limit_s=60)
    LABELS = ("Переобучение", "Недообучение", "Модель обучилась нормально")

    def draw(self, rng, label):
        if label == "Переобучение":
            train = rng.randint(93, 100)
            val = train - rng.randint(15, 35)
        elif label == "Недообучение":
            train = rng.randint(52, 66)
            val = train - rng.randint(0, 4)
        else:
            train = rng.randint(86, 96)
            val = train - rng.randint(0, 3)
        return {"train": train, "val": val, "metric": rng.choice(("accuracy", "F1", "ROC AUC")),
                "model": rng.choice(("градиентный бустинг", "случайный лес", "нейросеть", "логистическая регрессия",
                                     "SVM", "k-NN")),
                "task": rng.choice(("отток клиентов", "кредитный скоринг", "классификацию отзывов",
                                    "детекцию мошенничества", "прогноз покупки")),
                "epochs": rng.randint(5, 200)}

    def render(self, p):
        return (f"Модель «{p['model']}» для задачи «{p['task']}» обучали {p['epochs']} эпох/итераций. "
                f"{p['metric']} на обучающей выборке — {p['train']} %, на валидационной — {p['val']} %. "
                "Что вероятнее всего происходит?", None)

    def classify(self, inst: Instance):
        train, val = (int(x) for x in re.search(r"обучающей выборке — (\d+) %, на валидационной — (\d+) %",
                                                 inst.stem_md).groups())
        if train - val >= 10:
            return "Переобучение"
        if train < 75:
            return "Недообучение"
        return "Модель обучилась нормально"


class Groupby(TypedNumberFamily):
    """b = -0.5 (junior): groupby + mean/sum/count; pandas skips missing values (NaN) in all three,
    so count is the number of non-missing values, and mean divides by it."""

    meta = FamilyMeta(id="ml.data.groupby.v1", version=1, specs=M, topic="ml.data_processing",
                      skills=("pandas", "python"), format="code_output", a=1.1, b=-0.5, c=0.0, time_limit_s=120)
    DECIMALS = 2
    CITIES = ("Казань", "Омск", "Пермь", "Сочи", "Тула", "Уфа")

    def draw(self, rng):
        while True:
            cities = rng.sample(self.CITIES, 3)
            rows = [[rng.choice(cities), None if rng.random() < 0.2 else rng.randint(1, 50) * 10]
                    for _ in range(rng.randint(6, 9))]
            target = rng.choice(cities)
            vals = [v for c, v in rows if c == target and v is not None]
            agg = rng.choice(("mean", "sum", "count"))
            if vals:
                return {"rows": rows, "target": target, "agg": agg,
                        "col": rng.choice(("amount", "revenue", "price", "visits"))}

    def solve(self, p):
        vals = [v for c, v in p["rows"] if c == p["target"] and v is not None]
        return {"mean": sum(vals) / len(vals), "sum": sum(vals), "count": len(vals)}[p["agg"]]

    def render(self, p):
        cities = [r[0] for r in p["rows"]]
        values = ["np.nan" if r[1] is None else str(r[1]) for r in p["rows"]]
        code = ("import numpy as np\nimport pandas as pd\n\n"
                f"df = pd.DataFrame({{\n    'city': {cities},\n    '{p['col']}': [{', '.join(values)}],\n}})\n"
                f"print(df.groupby('city')['{p['col']}'].{p['agg']}()['{p['target']}'])")
        return "Что напечатает код?", {"lang": "python", "text": code}

    def oracle_value(self, inst):
        text = inst.code["text"]
        cities = re.findall(r"'([А-Яа-яЁё]+)'", re.search(r"'city': \[(.*?)\]", text).group(1))
        raw = re.search(r"'\w+': \[([\w., ]+)\],", text).group(1).split(", ")
        agg, target = re.search(r"\.(mean|sum|count)\(\)\['(\w+)'\]", text).groups()
        db = sqlite3.connect(":memory:")
        try:
            db.execute("CREATE TABLE t (city TEXT, v INTEGER)")
            db.executemany("INSERT INTO t VALUES (?, ?)",
                           [(c, None if v == "np.nan" else int(v)) for c, v in zip(cities, raw, strict=True)])
            sql = {"mean": "AVG(v)", "sum": "SUM(v)", "count": "COUNT(v)"}[agg]
            return float(db.execute(f"SELECT {sql} FROM t WHERE city = ?", (target,)).fetchone()[0])
        finally:
            db.close()


class Broadcast(RedrawChoiceFamily):
    """b = 0.4 (middle): shapes are aligned from the right; a dimension is compatible if equal or 1,
    and a missing leading dimension counts as 1. The result takes the larger size in each place.
    Every item is broadcastable: an "error" option made the answer guessable from its frequency
    (verify gate), so incompatible pairs are left to other items."""

    meta = FamilyMeta(id="ml.data.broadcast.v1", version=1, specs=M, topic="ml.data_processing",
                      skills=("numpy",), format="code_output", a=1.2, b=0.4, c=0.25, time_limit_s=90)

    def draw(self, rng):
        out = [rng.randint(2, 9) for _ in range(rng.randint(2, 4))]
        a, b = [], []
        for size in out:                          # each place: one side has the size, the other size or 1
            pair = rng.choice(((size, size), (size, 1), (1, size)))
            a.append(pair[0])
            b.append(pair[1])
        drop = rng.randint(0, len(out) - 1)       # missing leading dims on one side count as 1
        if rng.random() < 0.5:
            a = [x if i >= drop or b[i] == x else 1 for i, x in enumerate(a)][drop:] or a
        else:
            b = [x if i >= drop or a[i] == x else 1 for i, x in enumerate(b)][drop:] or b
        return {"a": a, "b": b, "op": rng.choice(("+", "*", "-")),
                "names": rng.choice((("a", "b"), ("x", "w"), ("u", "v"), ("m", "n"), ("img", "mask"),
                                     ("feat", "scale")))}

    @staticmethod
    def _shape(a, b):
        out = []
        for i in range(1, max(len(a), len(b)) + 1):
            x = a[-i] if i <= len(a) else 1
            y = b[-i] if i <= len(b) else 1
            if x != y and 1 not in (x, y):
                return None
            out.append(max(x, y))
        return tuple(reversed(out))

    def answer(self, p):
        return str(self._shape(p["a"], p["b"]))

    def misconceptions(self, p):
        a, b = p["a"], p["b"]
        longer, shorter = (a, b) if len(a) >= len(b) else (b, a)
        left = [max(x, y) for x, y in zip(longer, shorter, strict=False)] + longer[len(shorter):]   # left-aligned
        return [str(tuple(left)), str(tuple(longer))]

    def render(self, p):
        x, y = p["names"]
        code = (f"import numpy as np\n\n{x} = np.ones({tuple(p['a'])})\n{y} = np.ones({tuple(p['b'])})\n"
                f"print(({x} {p['op']} {y}).shape)")
        return "Что напечатает код?", {"lang": "python", "text": code}

    def oracle_answer(self, inst):
        import numpy as np
        shapes = [tuple(int(v) for v in m.split(",") if v.strip()) for m in
                  re.findall(r"np\.ones\(\(([\d, ]*)\)\)", inst.code["text"])]
        return str(np.broadcast_shapes(*shapes))


class ConvOutput(TypedNumberFamily):
    """b = 0.2 (lower middle): out = floor((in + 2·padding − kernel) / stride) + 1 per spatial
    dimension; the floor and the doubled padding are where people slip."""

    meta = FamilyMeta(id="ml.dl.conv_output.v1", version=1, specs=M, topic="ml.deep_learning",
                      skills=("deep_learning", "pytorch"), format="numeric_scenario", a=1.2, b=0.2, c=0.0,
                      time_limit_s=120)

    def draw(self, rng):
        while True:
            p = {"h": rng.randint(8, 64), "w": rng.randint(8, 64), "c_in": rng.choice((1, 3, 16, 32)),
                 "c_out": rng.choice((8, 16, 32, 64)), "k": rng.choice((1, 3, 5, 7)), "s": rng.randint(1, 3),
                 "pad": rng.randint(0, 3), "ask": rng.choice(("h", "w", "numel"))}
            if p["h"] + 2 * p["pad"] >= p["k"] and p["w"] + 2 * p["pad"] >= p["k"]:
                return p

    def solve(self, p):
        h = (p["h"] + 2 * p["pad"] - p["k"]) // p["s"] + 1
        w = (p["w"] + 2 * p["pad"] - p["k"]) // p["s"] + 1
        return {"h": h, "w": w, "numel": p["c_out"] * h * w}[p["ask"]]

    def render(self, p):
        ask = {"h": "высота выходной карты признаков", "w": "ширина выходной карты признаков",
               "numel": "число элементов выходного тензора для одного примера (C × H × W)"}[p["ask"]]
        code = (f"conv = nn.Conv2d(in_channels={p['c_in']}, out_channels={p['c_out']}, kernel_size={p['k']}, "
                f"stride={p['s']}, padding={p['pad']})\n"
                f"x = torch.randn(1, {p['c_in']}, {p['h']}, {p['w']})  # N, C, H, W\ny = conv(x)")
        return f"Какой будет {ask}?", {"lang": "python", "text": code}

    def oracle_value(self, inst):
        text = inst.code["text"]
        k, s, pad = (int(re.search(fr"{name}=(\d+)", text).group(1)) for name in ("kernel_size", "stride", "padding"))
        c_out = int(re.search(r"out_channels=(\d+)", text).group(1))
        h, w = (int(v) for v in re.search(r"randn\(1, \d+, (\d+), (\d+)\)", text).groups())

        def positions(n):                         # count where the kernel fits on the padded axis
            return sum(1 for start in range(0, n + 2 * pad - k + 1, s))
        oh, ow = positions(h), positions(w)
        if "высота" in inst.stem_md:
            return float(oh)
        if "ширина" in inst.stem_md:
            return float(ow)
        return float(c_out * oh * ow)


class ParamCount(TypedNumberFamily):
    """b = 0.7 (middle/senior): a Linear layer has in·out weights plus out biases; a Conv2d has
    c_in·c_out·k·k weights plus c_out biases; activations have none."""

    meta = FamilyMeta(id="ml.dl.param_count.v1", version=1, specs=M, topic="ml.deep_learning",
                      skills=("deep_learning", "pytorch"), format="numeric_scenario", a=1.2, b=0.7, c=0.0,
                      time_limit_s=150)

    def draw(self, rng):
        if rng.random() < 0.5:
            sizes = [rng.randint(2, 128) for _ in range(rng.randint(3, 4))]
            return {"kind": "mlp", "sizes": sizes, "bias": rng.random() < 0.8}
        return {"kind": "conv", "c_in": rng.choice((1, 3, 4, 8, 16)), "c_mid": rng.randint(2, 64),
                "c_out": rng.randint(2, 128), "k1": rng.choice((1, 3, 5, 7)), "k2": rng.choice((1, 3, 5)),
                "bias": rng.random() < 0.8}

    def solve(self, p):
        if p["kind"] == "mlp":
            s = p["sizes"]
            return sum(a * b + (b if p["bias"] else 0) for a, b in zip(s, s[1:], strict=False))
        first = p["c_in"] * p["c_mid"] * p["k1"] ** 2 + (p["c_mid"] if p["bias"] else 0)
        second = p["c_mid"] * p["c_out"] * p["k2"] ** 2 + (p["c_out"] if p["bias"] else 0)
        return first + second

    def render(self, p):
        b = "" if p["bias"] else ", bias=False"
        if p["kind"] == "mlp":
            s = p["sizes"]
            layers = []
            for i, (a, c) in enumerate(zip(s, s[1:], strict=False)):
                layers.append(f"    nn.Linear({a}, {c}{b}),")
                if i < len(s) - 2:
                    layers.append("    nn.ReLU(),")
        else:
            layers = [f"    nn.Conv2d({p['c_in']}, {p['c_mid']}, kernel_size={p['k1']}{b}),", "    nn.ReLU(),",
                      f"    nn.Conv2d({p['c_mid']}, {p['c_out']}, kernel_size={p['k2']}{b}),"]
        code = "model = nn.Sequential(\n" + "\n".join(layers) + "\n)"
        return "Сколько обучаемых параметров у модели?", {"lang": "python", "text": code}

    def oracle_value(self, inst):
        import numpy as np
        total = 0
        for line in inst.code["text"].split("\n"):
            bias = "bias=False" not in line
            if m := re.search(r"nn\.Linear\((\d+), (\d+)", line):
                a, c = (int(v) for v in m.groups())
                arrays = [np.zeros((c, a))] + ([np.zeros(c)] if bias else [])
            elif m := re.search(r"nn\.Conv2d\((\d+), (\d+), kernel_size=(\d+)", line):
                a, c, k = (int(v) for v in m.groups())
                arrays = [np.zeros((c, a, k, k))] + ([np.zeros(c)] if bias else [])
            else:
                continue
            total += sum(int(x.size) for x in arrays)
        return float(total)


FAMILIES = [Knn(), Gini(), FitDiagnosis(), Groupby(), Broadcast(), ConvOutput(), ParamCount()]
