"""Generate PDF fixtures for AI tests per AI.md AI-R10 and AI-5.

Generates 3 hero CVs with text streams using fpdf2 and Arial TTF font:
1. Backend Middle (Python, Django, FastAPI, PostgreSQL, Docker)
2. Frontend Junior (React, TypeScript, Next.js, Redux)
3. ML Senior (PyTorch, Computer Vision, Pandas, CatBoost, MLflow)
And 1 image-only (scanned) PDF that contains zero text stream (raises UnreadablePdf).

Dev-only tool, never imported by the app or the tests:
    pip install fpdf2 pillow
    python tools/make_fixture_pdfs.py            # FIXTURE_FONT=/path/to/font.ttf to override
Any TTF with Cyrillic works (DejaVu Sans on Linux, Arial on Windows).
"""
import io
import os
from pathlib import Path

from fpdf import FPDF
from PIL import Image

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "ai" / "fixtures" / "cv"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
FONT_CANDIDATES = [
    os.environ.get("FIXTURE_FONT", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def font_path() -> str:
    for candidate in FONT_CANDIDATES:
        if candidate and Path(candidate).exists():
            return candidate
    raise SystemExit("No Cyrillic TTF found: set FIXTURE_FONT=/path/to/font.ttf")


def create_text_pdf(text: str, filename: str) -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.add_font("CyrillicSans", "", font_path())
    pdf.set_font("CyrillicSans", size=11)
    for line in text.strip().splitlines():
        if not line.strip():
            pdf.ln(5)
        else:
            pdf.multi_cell(pdf.epw, 7, line)
    out_path = FIXTURES_DIR / filename
    pdf.output(str(out_path))
    print(f"Generated {out_path.name} ({out_path.stat().st_size} bytes)")


def create_scanned_pdf(filename: str) -> None:
    img = Image.new("RGB", (200, 200), color="white")
    img_buf = io.BytesIO()
    img.save(img_buf, format="PNG")
    img_buf.seek(0)

    pdf = FPDF()
    pdf.add_page()
    pdf.image(img_buf, x=10, y=10, w=100)
    out_path = FIXTURES_DIR / filename
    pdf.output(str(out_path))
    print(f"Generated scanned image-only PDF {out_path.name} ({out_path.stat().st_size} bytes)")


def main():
    # 1. Backend Middle Hero CV
    cv_backend = """Иванов Иван Иванович
Email: ivan.ivanov@example.com
Телефон: +7 (999) 111-22-33
Telegram: @ivan_backend
GitHub: https://github.com/ivan-dev
Город: Москва

Желаемая должность: Python Backend Developer
Опыт работы: 3.5 года
Формат работы: удаленно или гибрид
Ожидания по зарплате: от 220 000 до 280 000 руб на руки

Обо мне:
Опытный бэкенд разработчик на Python. Специализируюсь на создании отказоустойчивых REST API и микросервисов.

Опыт работы:
ООО Технологии Будущего (06.2021 — по н.в.)
Middle Python Разработчик
- Разработка сервисов на FastAPI и Django REST Framework (DRF)
- Проектирование схем и оптимизация запросов в PostgreSQL
- Развертывание сервисов в Docker и Kubernetes
- Асинхронные задачи с использованием Celery и Redis

Навыки:
Python, Django, FastAPI, PostgreSQL, Docker, Kubernetes, Redis, Celery, Git, Linux, REST API
"""
    create_text_pdf(cv_backend, "cv_backend_middle.pdf")

    # 2. Frontend Junior Hero CV
    cv_frontend = """Петрова Анна Сергеевна
Email: anna.petrova@example.com
Телефон: +7 (916) 444-55-66
Телеграм: @anna_frontend
Город: Санкт-Петербург

Желаемая должность: Frontend Developer
Опыт работы: 1 год
Формат: удаленка
Зарплатные ожидания: от 90 000 руб на руки

Обо мне:
Начинающий фронтенд разработчик с хорошей базой TypeScript и React.

Опыт работы:
Веб-Студия Старт (09.2023 — по н.в.)
Junior Frontend Разработчик
- Создание пользовательских интерфейсов на React и Next.js
- Типизация компонентов на TypeScript
- Верстка адаптивных макетов HTML, CSS, TailwindCSS

Навыки:
JavaScript, TypeScript, React, Next.js, Redux, HTML, CSS, TailwindCSS, Git
"""
    create_text_pdf(cv_frontend, "cv_frontend_junior.pdf")

    # 3. ML Senior Hero CV
    cv_ml = """Смирнов Дмитрий Алексеевич
Email: dmitry.smirnov@example.com
Телефон: +7 (903) 777-88-99
Telegram: @dmitry_ml
Город: Москва

Желаемая должность: Senior ML Engineer
Опыт работы: 6 лет
Формат работы: удаленный (remote)
Зарплата: от 400 000 руб на руки

Обо мне:
Ведущий инженер машинного обучения. Экспертиза в Computer Vision, Deep Learning и MLOps.

Опыт работы:
AI Innovations Lab (01.2020 — по н.в.)
Lead ML Engineer
- Разработка и обучение нейросетевых архитектур на PyTorch
- Построение пайплайнов детекции и сегментации с OpenCV
- Тюнинг гиперпараметров с Optuna, трекинг экспериментов в MLflow
- Табличные модели: CatBoost, XGBoost, LightGBM

Навыки:
Python, PyTorch, Machine Learning, Deep Learning, Computer Vision, OpenCV, Pandas, NumPy, CatBoost, MLflow, Docker
"""
    create_text_pdf(cv_ml, "cv_ml_senior.pdf")

    # 4. Scanned Image-only CV
    create_scanned_pdf("cv_scanned_image_only.pdf")


if __name__ == "__main__":
    main()
