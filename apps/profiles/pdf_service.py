"""Player Card PDF generator service with QR code validation."""

import base64
import io
import logging
from html import escape as html_escape

import qrcode
from django.conf import settings

logger = logging.getLogger(__name__)


def generate_qr_code_base64(url: str) -> str:
    """Generate a QR code as base64 PNG data URL."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1E3A8A", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def generate_player_card_pdf(candidate_profile) -> bytes:
    """Generate a branded Player Card PDF with verification QR code."""
    verify_url = f"{settings.PUBLIC_BASE_URL}/api/verify/{candidate_profile.public_id}"
    qr_base64 = generate_qr_code_base64(verify_url)

    # Get league membership
    league_qs = candidate_profile.user.league_memberships.all()
    if candidate_profile.specialization:
        league_qs = league_qs.filter(specialization=candidate_profile.specialization)
    league = league_qs.first()
    rating = league.rating if league else 1000
    grade = html_escape(str(league.grade).upper() if league else "UNRATED")
    spec = html_escape(str(league.specialization).upper() if league else "IT")
    status_label = html_escape(str(league.status).upper() if league else "PENDING")

    # Get FSP achievements
    fsp_results = list(candidate_profile.user.fsp_results.all())
    fsp_rank = ""
    if hasattr(candidate_profile.user, "fsp_link"):
        fsp_rank = html_escape(str(candidate_profile.user.fsp_link.sports_rank).upper())

    skills = [html_escape(cs.skill.name) for cs in candidate_profile.skills.all()[:10]]
    public_id = html_escape(str(candidate_profile.public_id))
    full_name = html_escape(str(candidate_profile.full_name or "Кандидат"))

    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Player Card - {public_id}</title>
<style>
    body {{
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        margin: 0;
        padding: 24px;
        color: #1e293b;
        background-color: #f8fafc;
    }}
    .card {{
        background: #ffffff;
        border: 2px solid #0284c7;
        border-radius: 12px;
        padding: 24px;
        max-width: 600px;
        margin: 0 auto;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }}
    .header {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 2px solid #e2e8f0;
        padding-bottom: 16px;
    }}
    .title {{
        font-size: 24px;
        font-weight: 800;
        color: #0369a1;
        margin: 0;
    }}
    .subtitle {{
        font-size: 14px;
        color: #64748b;
        margin-top: 4px;
    }}
    .public-id {{
        font-size: 18px;
        font-weight: bold;
        background: #e0f2fe;
        color: #0369a1;
        padding: 6px 12px;
        border-radius: 6px;
    }}
    .stats-grid {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 16px;
        margin: 20px 0;
    }}
    .stat-box {{
        background: #f1f5f9;
        padding: 12px;
        border-radius: 8px;
    }}
    .stat-label {{
        font-size: 12px;
        color: #64748b;
        text-transform: uppercase;
        font-weight: 600;
    }}
    .stat-value {{
        font-size: 20px;
        font-weight: 700;
        color: #0f172a;
        margin-top: 4px;
    }}
    .rating-badge {{
        color: #0284c7;
    }}
    .skills {{
        margin: 16px 0;
    }}
    .skill-chip {{
        display: inline-block;
        background: #e2e8f0;
        color: #334155;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 12px;
        margin: 2px;
    }}
    .fsp-section {{
        background: #fef3c7;
        border: 1px solid #f59e0b;
        border-radius: 8px;
        padding: 12px;
        margin: 16px 0;
    }}
    .footer {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-top: 1px solid #e2e8f0;
        padding-top: 16px;
        margin-top: 20px;
    }}
    .qr-container {{
        text-align: right;
    }}
    .qr-container img {{
        width: 90px;
        height: 90px;
    }}
    .verify-note {{
        font-size: 11px;
        color: #64748b;
    }}
</style>
</head>
<body>
<div class="card">
    <div class="header">
        <div>
            <h1 class="title">FSP DRAFT · КАРТОЧКА ИГРОКА</h1>
            <div class="subtitle">Федерация спортивного программирования</div>
        </div>
        <div class="public-id">{public_id}</div>
    </div>

    <div class="stats-grid">
        <div class="stat-box">
            <div class="stat-label">Лига и Грейд</div>
            <div class="stat-value">{spec} · {grade}</div>
            <small style="color: {"#16a34a" if status_label == "CONFIRMED" else "#ea580c"}">{status_label}</small>
        </div>
        <div class="stat-box">
            <div class="stat-label">Рейтинг силы (IRT)</div>
            <div class="stat-value rating-badge">{rating}</div>
            <small>Адаптивная квалификация</small>
        </div>
    </div>

    <div class="skills">
        <div class="stat-label" style="margin-bottom: 6px;">Стек и ключевые навыки:</div>
        {" ".join(f'<span class="skill-chip">{s}</span>' for s in skills) if skills else '<span style="color:#94a3b8">Навыки уточняются</span>'}
    </div>

    {'<div class="fsp-section"><strong>Достижения ФСП:</strong> ' + f"Разряд: {fsp_rank}. " + f"Турниров в реестре: {len(fsp_results)}</div>" if fsp_results or fsp_rank else ""}

    <div class="footer">
        <div>
            <div style="font-weight: 600;">{full_name}</div>
            <div class="verify-note">Верифицированный профиль FSP Draft</div>
            <div class="verify-note">Сканируйте QR-код для онлайн-проверки</div>
        </div>
        <div class="qr-container">
            <img src="data:image/png;base64,{qr_base64}" alt="QR verification">
        </div>
    </div>
</div>
</body>
</html>"""

    try:
        from weasyprint import HTML

        def _safe_url_fetcher(url, timeout=10, ssl_context=None):
            """Only allow data: URIs to prevent SSRF."""
            if url.startswith("data:"):
                from weasyprint import default_url_fetcher

                return default_url_fetcher(url, timeout=timeout, ssl_context=ssl_context)
            raise ValueError(f"External URL fetching is disabled: {url}")

        return HTML(string=html_content, url_fetcher=_safe_url_fetcher).write_pdf()
    except (ImportError, OSError) as e:
        logger.warning("weasyprint not available: %s", e)
        from core.errors import FSPAPIError

        raise FSPAPIError(
            "pdf_service_unavailable",
            "PDF Service Unavailable",
            "Player card PDF generation service is currently unavailable",
            503,
        )
    except Exception:
        logger.exception("PDF generation failed")
        from core.errors import FSPAPIError

        raise FSPAPIError(
            "pdf_generation_failed", "PDF Error", "Player card PDF generation failed", 503
        )
