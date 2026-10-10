"""ML & Data families on statistics and model metrics (typed answers).

ml.stats.center.v1     median or mean of a small sample (statistics module oracle)
ml.stats.bayes.v1      P(positive class | positive test) from base rate, TPR, TNR (count-based oracle)
ml.metrics.prf.v1      precision, recall or F1 from label lists (oracle recounts the confusion matrix)
ml.metrics.roc_auc.v1  ROC AUC of scores vs labels (oracle integrates the ROC curve; generator counts pairs)
"""
from __future__ import annotations

import re
import statistics
from fractions import Fraction

from ..base import FamilyMeta
from ..builder import TypedNumberFamily

M = ("ml_data",)


class Center(TypedNumberFamily):
    """b = -1.4 (intern/junior): the median of an even-sized sample is the mean of the two middle
    values after sorting; the mean is pulled by the outlier the sample sometimes contains."""

    meta = FamilyMeta(id="ml.stats.center.v1", version=1, specs=M, topic="ml.statistics",
                      skills=("machine_learning", "numpy"), format="numeric_scenario", a=1.0, b=-1.4, c=0.0,
                      time_limit_s=90)
    SEMANTIC = ('values', 'ask')
    DECIMALS = 2

    def draw(self, rng):
        n = rng.randint(6, 11)
        values = [rng.randint(1, 60) for _ in range(n)]
        if rng.random() < 0.4:
            values[rng.randrange(n)] = rng.randint(150, 900)        # an outlier
        return {"values": values, "ask": rng.choice(("median", "mean")),
                "what": rng.choice(("время ответа сервиса, мс", "чек покупателя, тыс. ₽", "длина сессии, мин",
                                    "число ошибок в сутки", "возраст клиента, лет", "задержка батча, с"))}

    def solve(self, p):
        v = sorted(p["values"])
        n = len(v)
        if p["ask"] == "mean":
            return sum(v) / n
        return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2

    def render(self, p):
        word = "медиану" if p["ask"] == "median" else "среднее арифметическое"
        return (f"Выборка ({p['what']}): {', '.join(str(x) for x in p['values'])}. Найдите {word}.", None)

    def oracle_value(self, inst):
        values = [int(x) for x in re.search(r"\): ([\d, ]+)\.", inst.stem_md).group(1).split(",")]
        return float(statistics.median(values) if "медиану" in inst.stem_md else statistics.fmean(values))


CONTEXTS = (("заболевание", "тест", "болен"), ("мошенническая транзакция", "антифрод-модель", "мошенническая"),
            ("спам", "спам-фильтр", "спам"), ("брак", "система контроля качества", "бракованная"),
            ("отток клиента", "модель оттока", "уходящий клиент"))


class Bayes(TypedNumberFamily):
    """b = 1.0 (senior boundary): with a low base rate most positives are false positives;
    the answer is TP / (TP + FP), not the sensitivity (base-rate neglect)."""

    meta = FamilyMeta(id="ml.stats.bayes.v1", version=1, specs=M, topic="ml.statistics",
                      skills=("machine_learning",), format="numeric_scenario", a=1.3, b=1.0, c=0.0,
                      time_limit_s=150)
    SEMANTIC = ('base', 'tpr', 'tnr')
    DECIMALS = 1

    def draw(self, rng):
        return {"base": rng.randint(10, 2000) / 100, "tpr": rng.randint(60, 99),
                "tnr": rng.randint(70, 99), "ctx": rng.randrange(len(CONTEXTS))}

    def solve(self, p):
        b, tpr, fpr = p["base"] / 100, p["tpr"] / 100, 1 - p["tnr"] / 100
        return 100 * b * tpr / (b * tpr + (1 - b) * fpr)

    def render(self, p):
        thing, detector, _ = CONTEXTS[p["ctx"]]
        base = f"{p['base']:g}".replace(".", ",")
        return (f"Доля объектов класса «{thing}» — {base} %. {detector[0].upper()}{detector[1:]} находит "
                f"{p['tpr']} % таких объектов (полнота) и правильно отклоняет {p['tnr']} % остальных "
                "(специфичность). Объект получил положительный результат. С какой вероятностью он действительно "
                "относится к этому классу? Ответ в процентах.", None)

    def oracle_value(self, inst):
        base, tpr, tnr = re.search(r"— ([\d,]+) %.*?находит (\d+) %.*?отклоняет (\d+) %", inst.stem_md).groups()
        population = 1_000_000                      # count people instead of multiplying probabilities
        pos = Fraction(base.replace(",", ".")) / 100 * population
        tp = pos * Fraction(int(tpr), 100)
        fp = (population - pos) * Fraction(100 - int(tnr), 100)
        return float(100 * tp / (tp + fp))


class PrecisionRecall(TypedNumberFamily):
    """b = -0.4 (upper junior): precision divides by predicted positives, recall by actual
    positives, F1 is their harmonic mean; swapping the denominators is the classic slip."""

    meta = FamilyMeta(id="ml.metrics.prf.v1", version=1, specs=M, topic="ml.metrics",
                      skills=("machine_learning", "scikit_learn"), format="numeric_scenario", a=1.2, b=-0.4,
                      c=0.0, time_limit_s=120)
    DECIMALS = 2

    def draw(self, rng):
        while True:
            n = rng.randint(12, 20)
            y_true = [int(rng.random() < 0.45) for _ in range(n)]
            y_pred = [t if rng.random() < 0.7 else 1 - t for t in y_true]
            tp = sum(1 for t, q in zip(y_true, y_pred, strict=True) if t == q == 1)
            if tp and sum(y_pred) and sum(y_true):
                return {"y_true": y_true, "y_pred": y_pred, "ask": rng.choice(("precision", "recall", "f1"))}

    def solve(self, p):
        tp = sum(1 for t, q in zip(p["y_true"], p["y_pred"], strict=True) if t == q == 1)
        precision = tp / sum(p["y_pred"])
        recall = tp / sum(p["y_true"])
        return {"precision": precision, "recall": recall,
                "f1": 2 * precision * recall / (precision + recall)}[p["ask"]]

    def render(self, p):
        name = {"precision": "precision (точность)", "recall": "recall (полноту)", "f1": "F1-меру"}[p["ask"]]
        code = f"y_true = {p['y_true']}\ny_pred = {p['y_pred']}"
        return f"Посчитайте {name} для положительного класса 1.", {"lang": "python", "text": code}

    def oracle_value(self, inst):
        y_true = [int(x) for x in re.search(r"y_true = \[([\d, ]+)\]", inst.code["text"]).group(1).split(",")]
        y_pred = [int(x) for x in re.search(r"y_pred = \[([\d, ]+)\]", inst.code["text"]).group(1).split(",")]
        confusion = {(t, q): 0 for t in (0, 1) for q in (0, 1)}
        for t, q in zip(y_true, y_pred, strict=True):
            confusion[(t, q)] += 1
        tp, fp, fn = confusion[(1, 1)], confusion[(0, 1)], confusion[(1, 0)]
        if "precision" in inst.stem_md:
            return tp / (tp + fp)
        if "recall" in inst.stem_md:
            return tp / (tp + fn)
        return 2 * tp / (2 * tp + fp + fn)


class RocAuc(TypedNumberFamily):
    """b = 1.3 (senior): AUC is the share of (positive, negative) pairs ranked correctly; doing it
    by hand means either counting pairs or integrating the ROC staircase."""

    meta = FamilyMeta(id="ml.metrics.roc_auc.v1", version=1, specs=M, topic="ml.metrics",
                      skills=("machine_learning", "scikit_learn"), format="numeric_scenario", a=1.3, b=1.3,
                      c=0.0, time_limit_s=180)
    DECIMALS = 3

    def draw(self, rng):
        while True:
            n = rng.randint(6, 9)
            scores = rng.sample(range(5, 100, 5), n)
            labels = [int(rng.random() < 0.5) for _ in range(n)]
            if 0 < sum(labels) < n:
                return {"scores": [s / 100 for s in scores], "labels": labels}

    def solve(self, p):
        pos = [s for s, y in zip(p["scores"], p["labels"], strict=True) if y]
        neg = [s for s, y in zip(p["scores"], p["labels"], strict=True) if not y]
        return sum(1 for a in pos for b in neg if a > b) / (len(pos) * len(neg))

    def render(self, p):
        code = f"scores = {p['scores']}\nlabels = {p['labels']}"
        return "Посчитайте ROC AUC модели (все значения scores различны).", {"lang": "python", "text": code}

    def oracle_value(self, inst):
        scores = [float(x) for x in re.search(r"scores = \[([\d., ]+)\]", inst.code["text"]).group(1).split(",")]
        labels = [int(x) for x in re.search(r"labels = \[([\d, ]+)\]", inst.code["text"]).group(1).split(",")]
        ranked = [y for _, y in sorted(zip(scores, labels, strict=True), reverse=True)]
        n_pos, n_neg = sum(labels), len(labels) - sum(labels)
        tpr = fpr = 0
        area = Fraction(0)
        for y in ranked:                         # walk the threshold down; add trapezoids
            if y:
                tpr += 1
            else:
                area += Fraction(tpr, n_pos) * Fraction(1, n_neg)
                fpr += 1
        return float(area)


FAMILIES = [Center(), Bayes(), PrecisionRecall(), RocAuc()]
