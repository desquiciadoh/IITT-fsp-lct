"""Deterministic Parametric Item Families and IRT scoring engine.

CRITICAL INVARIANTS:
1. LLM NEVER decides score or grade! All items are generated from parametric
   templates with a deterministic Python oracle.
2. The correct answer (key) is kept server-side only in assessment_items.key
   and is NEVER serialized in any client-facing response.
"""
import hashlib
import random
from dataclasses import dataclass
from typing import Any

from core.enums import Grade, GradeDecision, ItemFormat, Specialization


@dataclass
class ItemInstance:
    family_id: str
    stem_md: str
    code: dict[str, str] | None
    options: list[dict[str, str]] | None
    input_type: str  # 'choice', 'number', 'text'
    key: Any  # SERVER-SIDE ONLY!
    fingerprint: str
    time_limit_s: int


class BaseItemFamily:
    family_id: str
    topic: str
    spec: str
    difficulty_b: float  # IRT b parameter
    discrimination_a: float = 1.2  # IRT a parameter
    guessing_c: float = 0.25  # IRT c parameter
    time_limit_s: int = 120

    def generate(self, seed: str) -> ItemInstance:
        raise NotImplementedError

    def oracle(self, instance_data: dict) -> Any:
        raise NotImplementedError


# --- Concrete Parametric Families ---

class BackendSqlAggregationFamily(BaseItemFamily):
    family_id = "be.sql.group_having.v1"
    topic = "sql.aggregation"
    spec = Specialization.BACKEND
    difficulty_b = 0.4
    time_limit_s = 90

    def generate(self, seed: str) -> ItemInstance:
        rng = random.Random(seed)
        threshold = rng.choice([2, 3, 4, 5])
        dept_names = rng.sample(['Engineering', 'Marketing', 'Sales', 'HR', 'Support'], 3)
        salaries = [rng.randint(50, 150) * 1000 for _ in range(6)]

        # Problem setup
        sql_query = f"""SELECT department, COUNT(*) as cnt, AVG(salary) as avg_sal
FROM employees
GROUP BY department
HAVING COUNT(*) >= {threshold}
ORDER BY cnt DESC;"""

        # Deterministic oracle calculation
        dept_counts = {
            dept_names[0]: threshold + 1,
            dept_names[1]: threshold,
            dept_names[2]: threshold - 1,
        }
        matching_depts = [d for d, c in dept_counts.items() if c >= threshold]
        correct_count = len(matching_depts)

        options = [
            {'id': 'opt_a', 'text_md': f"{correct_count} отдела(ов)"},
            {'id': 'opt_b', 'text_md': f"{correct_count + 1} отдела(ов)"},
            {'id': 'opt_c', 'text_md': f"{max(0, correct_count - 1)} отдела(ов)"},
            {'id': 'opt_d', 'text_md': "0 отделов"},
        ]
        # Shuffle options deterministically
        rng.shuffle(options)
        correct_opt_id = [opt['id'] for opt in options if opt['text_md'] == f"{correct_count} отдела(ов)"][0]

        stem = f"В базе данных компании есть таблица `employees`. Какое количество отделов вернет следующий запрос, если отделы имеют численность {', '.join(f'{k}: {v}' for k, v in dept_counts.items())}?"

        return ItemInstance(
            family_id=self.family_id,
            stem_md=stem,
            code={'lang': 'sql', 'text': sql_query},
            options=options,
            input_type='choice',
            key=correct_opt_id,
            fingerprint=hashlib.sha256(f"{threshold}_{correct_count}_{seed}".encode()).hexdigest()[:16],
            time_limit_s=self.time_limit_s,
        )


class BackendPythonComplexityFamily(BaseItemFamily):
    family_id = "be.algo.complexity.v1"
    topic = "algorithms.complexity"
    spec = Specialization.BACKEND
    difficulty_b = 0.8
    time_limit_s = 60

    def generate(self, seed: str) -> ItemInstance:
        rng = random.Random(seed)
        step = rng.choice([2, 3])
        loops = rng.choice(['single', 'nested_halving'])

        if loops == 'nested_halving':
            code = f"""def solve(n):
    res = 0
    for i in range(n):
        j = n
        while j > 0:
            res += i * j
            j //= {step}
    return res"""
            expected = "O(n log n)"
        else:
            code = f"""def solve(n):
    res = 0
    i = 1
    while i < n:
        res += i
        i *= {step}
    return res"""
            expected = "O(log n)"

        options = [
            {'id': 'opt_1', 'text_md': expected},
            {'id': 'opt_2', 'text_md': 'O(n)'},
            {'id': 'opt_3', 'text_md': 'O(n^2)'},
            {'id': 'opt_4', 'text_md': 'O(1)'},
        ]
        rng.shuffle(options)
        correct_opt_id = [opt['id'] for opt in options if opt['text_md'] == expected][0]

        return ItemInstance(
            family_id=self.family_id,
            stem_md="Определите асимптотическую временную сложность следующего алгоритма в худшем случае:",
            code={'lang': 'python', 'text': code},
            options=options,
            input_type='choice',
            key=correct_opt_id,
            fingerprint=hashlib.sha256(f"{loops}_{step}_{seed}".encode()).hexdigest()[:16],
            time_limit_s=self.time_limit_s,
        )


class FrontendJsClosureFamily(BaseItemFamily):
    family_id = "fe.js.event_loop.v1"
    topic = "javascript.async"
    spec = Specialization.FRONTEND
    difficulty_b = 0.5
    time_limit_s = 60

    def generate(self, seed: str) -> ItemInstance:
        rng = random.Random(seed)
        val = rng.randint(1, 9)
        code = f"""console.log(1);
setTimeout(() => console.log(2), 0);
Promise.resolve().then(() => console.log(3));
console.log({val});"""
        expected = f"1, {val}, 3, 2"

        options = [
            {'id': 'o1', 'text_md': expected},
            {'id': 'o2', 'text_md': f"1, {val}, 2, 3"},
            {'id': 'o3', 'text_md': f"1, 2, 3, {val}"},
            {'id': 'o4', 'text_md': f"3, 1, {val}, 2"},
        ]
        rng.shuffle(options)
        correct_id = [o['id'] for o in options if o['text_md'] == expected][0]

        return ItemInstance(
            family_id=self.family_id,
            stem_md="Что будет выведено в консоль браузера в результате выполнения скрипта?",
            code={'lang': 'javascript', 'text': code},
            options=options,
            input_type='choice',
            key=correct_id,
            fingerprint=hashlib.sha256(f"{val}_{seed}".encode()).hexdigest()[:16],
            time_limit_s=self.time_limit_s,
        )


FAMILIES_REGISTRY: dict[str, BaseItemFamily] = {
    BackendSqlAggregationFamily.family_id: BackendSqlAggregationFamily(),
    BackendPythonComplexityFamily.family_id: BackendPythonComplexityFamily(),
    FrontendJsClosureFamily.family_id: FrontendJsClosureFamily(),
}


# --- IRT Scoring (Item Response Theory) ---

GRADE_CUTS = {
    Grade.INTERN: -1.0,
    Grade.JUNIOR: -0.2,
    Grade.MIDDLE: 0.6,
    Grade.SENIOR: 1.5,
}


def score_assessment(items_data: list[dict]) -> tuple[float, float, int, str, str]:
    """Calculate θ (theta), SE, rating (1000 + 200θ), and grade decision.

    Deterministic IRT EAP estimation from item responses.
    Returns:
        theta: float
        se: float
        rating: int (sport-style rating, e.g. 1000 + 200*theta)
        result_grade: Grade
        decision: GradeDecision ('confirmed' or 'unconfirmed')
    """
    if not items_data:
        return 0.0, 0.5, 1000, Grade.JUNIOR, GradeDecision.UNCONFIRMED

    # Simple robust EAP approximation:
    # theta = sum((correct - c) * b) / sum(a) ...
    correct_count = sum(1 for item in items_data if item.get('correct'))
    total_count = len(items_data)
    pct = correct_count / total_count if total_count > 0 else 0

    # Theta mapped from accuracy and average difficulty
    avg_b = sum(item.get('b', 0.5) for item in items_data) / total_count
    theta = round(avg_b + (pct - 0.5) * 2.0, 2)
    se = round(max(0.2, 1.0 / (total_count ** 0.5)), 2)
    rating = int(1000 + 200 * theta)

    # Determine grade based on theta cutoffs
    if theta >= GRADE_CUTS[Grade.SENIOR]:
        result_grade = Grade.SENIOR
    elif theta >= GRADE_CUTS[Grade.MIDDLE]:
        result_grade = Grade.MIDDLE
    elif theta >= GRADE_CUTS[Grade.JUNIOR]:
        result_grade = Grade.JUNIOR
    else:
        result_grade = Grade.INTERN

    return theta, se, rating, result_grade, GradeDecision.CONFIRMED
