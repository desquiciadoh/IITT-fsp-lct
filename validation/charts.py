"""Pure Python SVG chart generator for the Validation Lab (ML-8).

Renders vector charts into validation/out/charts/ with zero external graphics dependencies:
  - confusion.svg: 4x4 classification confusion matrix with counts;
  - tif.svg: Test Information Function curve across ability θ with cut score markers;
  - leak_attack.svg: Cheater θ inflation comparison (static bank vs parametric families);
  - matching.svg: nDCG@10 and P@10 comparison across 5 candidate ranking systems.

Pure: no matplotlib, no Cairo, no external libraries.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from assessment.families.base import GRADES

GRADE_LABELS = ("Intern", "Junior", "Middle", "Senior")


def render_confusion_svg(confusion: list[list[int]], out_path: Path) -> None:
    """Render 4x4 confusion matrix heatmap in SVG."""
    width, height = 520, 440
    margin_left, margin_top = 100, 70
    cell_size = 75

    max_val = max(max(row) for row in confusion) if confusion else 1
    max_val = max(1, max_val)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
        '  <rect width="100%" height="100%" fill="#ffffff" />',
        '  <style>',
        '    .title { font-family: system-ui, sans-serif; font-size: 16px; font-weight: bold; fill: #1e293b; }',
        '    .subtitle { font-family: system-ui, sans-serif; font-size: 11px; fill: #64748b; }',
        '    .label { font-family: system-ui, sans-serif; font-size: 12px; fill: #334155; }',
        '    .cell-text { font-family: system-ui, sans-serif; font-size: 14px; font-weight: bold; text-anchor: middle; dominant-baseline: middle; }',
        '  </style>',
        f'  <text x="{width // 2}" y="28" text-anchor="middle" class="title">Матрица ошибок классификации грейдов</text>',
        f'  <text x="{width // 2}" y="48" text-anchor="middle" class="subtitle">Строки: Истинный грейд · Столбцы: Присвоенный грейд</text>',
    ]

    # Column headers
    for j, label in enumerate(GRADE_LABELS):
        x = margin_left + j * cell_size + cell_size // 2
        lines.append(f'  <text x="{x}" y="{margin_top - 12}" text-anchor="middle" class="label">{label}</text>')

    # Row headers and cells
    for i, row in enumerate(confusion):
        y = margin_top + i * cell_size
        y_text = y + cell_size // 2
        lines.append(f'  <text x="{margin_left - 12}" y="{y_text + 4}" text-anchor="end" class="label">{GRADE_LABELS[i]}</text>')

        for j, val in enumerate(row):
            x = margin_left + j * cell_size
            ratio = val / max_val
            # Color gradient: pale blue to deep indigo
            r = int(240 - 180 * ratio)
            g = int(244 - 150 * ratio)
            b = int(255 - 70 * ratio)
            fill_color = f"rgb({r},{g},{b})"
            text_color = "#ffffff" if ratio > 0.55 else "#1e293b"

            lines.append(f'  <rect x="{x}" y="{y}" width="{cell_size}" height="{cell_size}" rx="4" fill="{fill_color}" stroke="#cbd5e1" stroke-width="1" />')
            lines.append(f'  <text x="{x + cell_size // 2}" y="{y + cell_size // 2 + 1}" fill="{text_color}" class="cell-text">{val}</text>')

    lines.append('</svg>')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def render_tif_svg(tif_data: dict[str, list[float]], out_path: Path) -> None:
    """Render Test Information Function curve with grade cut lines."""
    width, height = 560, 360
    margin_l, margin_r = 60, 40
    margin_t, margin_b = 60, 50

    thetas = tif_data["theta"]
    infos = tif_data["info"]

    max_info = max(infos) * 1.15 if infos else 10.0
    min_th, max_th = min(thetas), max(thetas)

    def tx(th: float) -> float:
        return margin_l + (th - min_th) / (max_th - min_th) * (width - margin_l - margin_r)

    def ty(inf: float) -> float:
        return height - margin_b - (inf / max_info) * (height - margin_t - margin_b)

    pts = " ".join(f"{tx(th):.1f},{ty(inf):.1f}" for th, inf in zip(thetas, infos))

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
        '  <rect width="100%" height="100%" fill="#ffffff" />',
        '  <style>',
        '    .title { font-family: system-ui, sans-serif; font-size: 15px; font-weight: bold; fill: #1e293b; }',
        '    .subtitle { font-family: system-ui, sans-serif; font-size: 11px; fill: #64748b; }',
        '    .axis { stroke: #cbd5e1; stroke-width: 1.5; }',
        '    .grid { stroke: #f1f5f9; stroke-width: 1; }',
        '    .cut-line { stroke: #e11d48; stroke-dasharray: 4 4; stroke-width: 1.5; }',
        '    .tick-text { font-family: system-ui, sans-serif; font-size: 10px; fill: #64748b; }',
        '    .legend { font-family: system-ui, sans-serif; font-size: 11px; fill: #334155; }',
        '  </style>',
        f'  <text x="{width // 2}" y="25" text-anchor="middle" class="title">Функция информации теста (TIF curve)</text>',
        f'  <text x="{width // 2}" y="42" text-anchor="middle" class="subtitle">Максимум информации на границах грейдов (θ = -1.0, 0.0, +1.0)</text>',
    ]

    # Grid lines and axes
    for th in (-2.0, -1.0, 0.0, 1.0, 2.0):
        x = tx(th)
        lines.append(f'  <line x1="{x:.1f}" y1="{margin_t}" x2="{x:.1f}" y2="{height - margin_b}" class="grid" />')
        lines.append(f'  <text x="{x:.1f}" y="{height - margin_b + 16}" text-anchor="middle" class="tick-text">{th:+.1f}</text>')

    # Vertical cut lines
    for cut_th, label in ((-1.0, "Jun"), (0.0, "Mid"), (1.0, "Sen")):
        x = tx(cut_th)
        lines.append(f'  <line x1="{x:.1f}" y1="{margin_t}" x2="{x:.1f}" y2="{height - margin_b}" class="cut-line" />')
        lines.append(f'  <text x="{x:.1f}" y="{margin_t - 6}" text-anchor="middle" fill="#e11d48" font-size="10" font-family="sans-serif">{label} cut</text>')

    # TIF polyline and points
    lines.append(f'  <polyline fill="none" stroke="#2563eb" stroke-width="3" points="{pts}" />')
    for th, inf in zip(thetas, infos):
        lines.append(f'  <circle cx="{tx(th):.1f}" cy="{ty(inf):.1f}" r="3.5" fill="#1d4ed8" />')

    lines.append('</svg>')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def render_leak_attack_svg(leak_attack: list[dict[str, Any]], out_path: Path) -> None:
    """Render leak attack grouped bar chart comparing static bank vs parametric families."""
    width, height = 560, 340
    margin_l, margin_r = 70, 30
    margin_t, margin_b = 60, 50

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
        '  <rect width="100%" height="100%" fill="#ffffff" />',
        '  <style>',
        '    .title { font-family: system-ui, sans-serif; font-size: 15px; font-weight: bold; fill: #1e293b; }',
        '    .subtitle { font-family: system-ui, sans-serif; font-size: 11px; fill: #64748b; }',
        '    .bar-static { fill: #ef4444; }',
        '    .bar-param { fill: #10b981; }',
        '    .label { font-family: system-ui, sans-serif; font-size: 12px; fill: #334155; }',
        '    .val-text { font-family: system-ui, sans-serif; font-size: 11px; font-weight: bold; }',
        '  </style>',
        f'  <text x="{width // 2}" y="25" text-anchor="middle" class="title">Стойкость к утечке: инфляция способности Δθ</text>',
        f'  <text x="{width // 2}" y="42" text-anchor="middle" class="subtitle">Статичный банк вопросов (красный) против параметрических семейств (зелёный)</text>',
    ]

    # Zero baseline
    zero_y = height // 2 + 20
    lines.append(f'  <line x1="{margin_l}" y1="{zero_y}" x2="{width - margin_r}" y2="{zero_y}" stroke="#94a3b8" stroke-width="1.5" />')
    lines.append(f'  <text x="{margin_l - 10}" y="{zero_y + 4}" text-anchor="end" class="label">Δθ = 0</text>')

    group_w = (width - margin_l - margin_r) / len(leak_attack)
    bar_w = 32

    scale_y = 120.0  # pixels per 1.0 delta theta

    for i, row in enumerate(leak_attack):
        gx = margin_l + i * group_w + group_w / 2
        pct_label = f"{int(row['leak_share'] * 100)}% утечки"
        lines.append(f'  <text x="{gx}" y="{height - 15}" text-anchor="middle" class="label">{pct_label}</text>')

        # Static bar (positive inflation, upward)
        s_dth = row["static_dtheta"]
        s_h = abs(s_dth) * scale_y
        s_x = gx - bar_w - 4
        s_y = zero_y - s_h if s_dth >= 0 else zero_y
        lines.append(f'  <rect x="{s_x}" y="{s_y}" width="{bar_w}" height="{max(2.0, s_h)}" rx="3" class="bar-static" />')
        lines.append(f'  <text x="{s_x + bar_w // 2}" y="{s_y - 6}" text-anchor="middle" class="val-text" fill="#b91c1c">+{s_dth:.2f}</text>')

        # Parametric bar (near zero or negative, downward)
        p_dth = row["parametric_dtheta"]
        p_h = abs(p_dth) * scale_y
        p_x = gx + 4
        p_y = zero_y - p_h if p_dth >= 0 else zero_y
        lines.append(f'  <rect x="{p_x}" y="{p_y}" width="{bar_w}" height="{max(2.0, p_h)}" rx="3" class="bar-param" />')
        p_text_y = p_y - 6 if p_dth >= 0 else p_y + p_h + 14
        lines.append(f'  <text x="{p_x + bar_w // 2}" y="{p_text_y}" text-anchor="middle" class="val-text" fill="#047857">{p_dth:+.2f}</text>')

    lines.append('</svg>')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def render_matching_svg(systems: list[dict[str, Any]], out_path: Path) -> None:
    """Render matching benchmark comparison across 5 systems."""
    width, height = 620, 360
    margin_l, margin_r = 140, 40
    margin_t, margin_b = 60, 40

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
        '  <rect width="100%" height="100%" fill="#ffffff" />',
        '  <style>',
        '    .title { font-family: system-ui, sans-serif; font-size: 15px; font-weight: bold; fill: #1e293b; }',
        '    .subtitle { font-family: system-ui, sans-serif; font-size: 11px; fill: #64748b; }',
        '    .label { font-family: system-ui, sans-serif; font-size: 12px; fill: #334155; }',
        '    .val-text { font-family: system-ui, sans-serif; font-size: 11px; font-weight: bold; fill: #1e293b; }',
        '  </style>',
        f'  <text x="{width // 2}" y="25" text-anchor="middle" class="title">Качество матчинга: nDCG@10 и Precision@10</text>',
        f'  <text x="{width // 2}" y="42" text-anchor="middle" class="subtitle">Сравнение 5 подходов против скрытого оракула истинной компетенции</text>',
    ]

    labels = {
        "keyword": "1. Keyword (резюме)",
        "bm25": "2. BM25 (текст JD)",
        "embeddings_only": "3. Эмбеддинги",
        "ours_no_verified": "4. Наш (без тестов)",
        "ours": "5. Наш итоговый (с тестами)",
    }

    n_sys = len(systems)
    slot_h = (height - margin_t - margin_b) / n_sys
    bar_h = 16
    plot_w = width - margin_l - margin_r

    for i, s in enumerate(systems):
        y = margin_t + i * slot_h
        name = s.get("name", "")
        display_name = labels.get(name, name)
        lines.append(f'  <text x="{margin_l - 12}" y="{y + slot_h // 2 + 4}" text-anchor="end" class="label">{display_name}</text>')

        # Bar 1: nDCG@10 (blue)
        ndcg = s.get("ndcg10", 0.0)
        bw1 = ndcg * plot_w
        by1 = y + slot_h // 2 - bar_h - 1
        lines.append(f'  <rect x="{margin_l}" y="{by1}" width="{bw1}" height="{bar_h}" rx="3" fill="#3b82f6" />')
        lines.append(f'  <text x="{margin_l + bw1 + 6}" y="{by1 + 12}" class="val-text">{ndcg:.3f}</text>')

        # Bar 2: P@10 (purple)
        p10 = s.get("p10", 0.0)
        bw2 = p10 * plot_w
        by2 = y + slot_h // 2 + 3
        lines.append(f'  <rect x="{margin_l}" y="{by2}" width="{bw2}" height="{bar_h}" rx="3" fill="#8b5cf6" />')
        lines.append(f'  <text x="{margin_l + bw2 + 6}" y="{by2 + 12}" class="val-text">{p10:.3f}</text>')

    # Legend
    lines.append(f'  <rect x="{width - 220}" y="{height - 20}" width="12" height="12" fill="#3b82f6" rx="2" />')
    lines.append(f'  <text x="{width - 202}" y="{height - 10}" class="label" font-size="11">nDCG@10</text>')
    lines.append(f'  <rect x="{width - 120}" y="{height - 20}" width="12" height="12" fill="#8b5cf6" rx="2" />')
    lines.append(f'  <text x="{width - 102}" y="{height - 10}" class="label" font-size="11">Precision@10</text>')

    lines.append('</svg>')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def generate_all_charts(report_data: dict[str, Any], out_dir: Path) -> list[Path]:
    """Generate all SVG charts into out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    if "assessment" in report_data:
        a = report_data["assessment"]
        if "confusion" in a:
            p = out_dir / "confusion.svg"
            render_confusion_svg(a["confusion"], p)
            paths.append(p)
        if "tif" in a:
            p = out_dir / "tif.svg"
            render_tif_svg(a["tif"], p)
            paths.append(p)
        if "leak_attack" in a:
            p = out_dir / "leak_attack.svg"
            render_leak_attack_svg(a["leak_attack"], p)
            paths.append(p)

    if "matching" in report_data and "systems" in report_data["matching"]:
        p = out_dir / "matching.svg"
        render_matching_svg(report_data["matching"]["systems"], p)
        paths.append(p)

    return paths
