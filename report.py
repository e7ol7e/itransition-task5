"""Paginated, self-contained PDF evidence from exactly the displayed snapshot."""
from __future__ import annotations

import io
from datetime import datetime, timezone
from xml.sax.saxutils import escape

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether

from analytics import METHODS

INK = colors.HexColor('#173e36')
PALETTE = ['#267761', '#cf9d35', '#5c82a0', '#a0779b', '#cf765c', '#8c9d56', '#618d94', '#a86673', '#6e74a2', '#a48b5e', '#679368', '#b57f44']
STYLES = getSampleStyleSheet()
STYLES.add(ParagraphStyle('ReportTitle', fontName='Helvetica-Bold', fontSize=34, leading=38, textColor=INK, spaceAfter=18))
STYLES.add(ParagraphStyle('Kicker', fontSize=9, leading=14, textColor=INK, spaceAfter=8))
STYLES.add(ParagraphStyle('SmallReport', fontSize=8, leading=12, textColor=colors.HexColor('#52635d'), spaceAfter=7))
STYLES['Heading1'].textColor = INK
STYLES['Heading2'].textColor = INK
STYLES['BodyText'].leading = 15
STYLES.add(ParagraphStyle('TableHeading', fontSize=8, leading=12, textColor=colors.white, spaceAfter=7))
from pathlib import Path
FONT_DIR=Path(matplotlib.get_data_path())/'fonts/ttf'
pdfmetrics.registerFont(TTFont('DejaVuSans', str(FONT_DIR/'DejaVuSans.ttf')))
pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', str(FONT_DIR/'DejaVuSans-Bold.ttf')))
for name,style in STYLES.byName.items():
    style.fontName = 'DejaVuSans-Bold' if name.startswith('Heading') or name in {'ReportTitle','TableHeading'} else 'DejaVuSans'


def para(text, style='BodyText'):
    return Paragraph(escape(str(text)), STYLES[style])


def table(rows, widths=None):
    cells = [[para(v, 'TableHeading' if index==0 else 'SmallReport') for v in row] for index,row in enumerate(rows)]
    item = Table(cells, colWidths=widths, repeatRows=1, hAlign='LEFT')
    item.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), INK), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f0f4ef'), colors.white]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8), ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5), ('LINEBELOW', (0, 0), (-1, 0), 1, INK),
    ]))
    return item


def chart(result, series=None, start=None, end=None, height=65):
    dates = result['source']['dates']
    start = 0 if start is None else start
    end = len(dates) if end is None else end
    xs = np.arange(start, end)
    fig, ax = plt.subplots(figsize=(7.2, height / 25.4), layout='constrained')
    fig.patch.set_facecolor('white')
    kind = result['settings']['chart_type']
    if series is None:
        if kind == 'stacked':
            ax.stackplot(xs, *[s['values'][start:end] for s in result['series'][1:]],
                         colors=PALETTE, labels=[s['name'] for s in result['series'][1:]], alpha=.8)
            subjects = [result['series'][0]]
        else:
            subjects = result['series'][1:]
    else:
        subjects = [series]
    for index, s in enumerate(subjects):
        y = s['values'][start:end]
        color = PALETTE[index % len(PALETTE)]
        if kind == 'bar':
            width = .8 / len(subjects)
            ax.bar(xs - .4 + width * (index + .5), y, width=width, color=color, alpha=.7, label=s['name'])
        elif not (series is None and kind == 'stacked'):
            if kind == 'stacked':
                ax.fill_between(xs, y, color=color, alpha=.15)
            ax.plot(xs, y, color=color, linewidth=1, label=s['name'])
        ax.plot(xs, s['trend'][start:end], color=color, linestyle='--', linewidth=1.4, label=f"{s['name']} trend")
        for direction, marker, flag_color in [('Spike', '^', '#b85e2d'), ('Drop', 'v', '#ad4050')]:
            points = [p for p in s['anomalies'] if start <= p['index'] < end and p['direction'] == direction]
            if points:
                ax.scatter([p['index'] for p in points], [p['value'] for p in points], color=flag_color, marker=marker, s=23, zorder=6)
    ticks = np.unique(np.linspace(start, max(start, end - 1), min(6, end-start), dtype=int))
    ax.set_xticks(ticks, [dates[i] for i in ticks], fontsize=7)
    ax.tick_params(axis='y', labelsize=7)
    ax.set_ylabel('Tonnes / day', fontsize=8)
    ax.grid(axis='y', alpha=.18)
    ax.spines[['top', 'right']].set_visible(False)
    if series is None:
        ax.legend(fontsize=6, ncol=3, loc='upper left', frameon=False)
    buffer = io.BytesIO()
    fig.savefig(buffer, format='png', dpi=145)
    plt.close(fig)
    buffer.seek(0)
    return Image(buffer, width=174*mm, height=height*mm)


def build_pdf(result):
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=18*mm, rightMargin=18*mm,
                            topMargin=24*mm, bottomMargin=20*mm,
                            title='Weyland-Yutani | Mining operations report', author='Mining Observatory')
    source, settings = result['source'], result['settings']
    total = result['series'][0]
    f = lambda v: f'{v:,.2f}'
    story = [Spacer(1, 8*mm), para('WEYLAND-YUTANI / RESOURCE INTELLIGENCE', 'Kicker'),
             para('Mining operations\nIntelligence report'.replace('\n', ' / '), 'ReportTitle'),
             para(f"{source['dates'][0]} — {source['dates'][-1]} | {len(source['dates'])} daily observations | {len(source['mines'])} mines", 'Kicker'),
             Spacer(1, 5*mm), chart(result, None if settings['chart_type']=='stacked' else total, height=70), Spacer(1, 4*mm),
             table([['Network production', 'Mean daily output', 'Flagged mine-days'],
                    [f(total['stats']['total'])+' t', f(total['stats']['mean'])+' t/day', str(result['anomaly_count'])]], [58*mm]*3),
             Spacer(1, 5*mm), para('An auditable view of daily extraction, dispersion and statistical anomalies. Every chart and table uses one immutable fetched snapshot; refreshing the Google Sheet does not change this report.', 'BodyText'),
             Spacer(1, 5*mm), para(f"Snapshot {source['snapshot']} | Fetched {source['fetched_at']}", 'SmallReport'),
             para(f"Generator: {source.get('sheet_url', '')}", 'SmallReport'),
             para(f"Prepared {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", 'SmallReport'), PageBreak(),
             para('01 / Statistical overview', 'Heading1'),
             para('Sample standard deviation; linearly interpolated quartiles. Total is calculated by summing the active mines for each date.', 'SmallReport')]
    rows = [['Series', 'Mean', 'Std dev', 'Median', 'IQR', 'Flags']]
    for s in result['series']:
        rows.append([s['name'], *[f(s['stats'][k]) for k in ['mean','std','median','iqr']], str(len(s['anomalies']))])
    story += [table(rows, [44*mm, 27*mm, 27*mm, 27*mm, 27*mm, 22*mm]), Spacer(1, 7*mm),
              para('02 / Detection settings & interpretation', 'Heading1')]
    rows = [['Test', 'Rule / parameter']]
    rows += [['IQR rule', f"Outside Q1 - {settings['iqr_factor']} x IQR or Q3 + {settings['iqr_factor']} x IQR"],
             ['Z-score', f"Absolute deviation / sample SD > {settings['z_threshold']}"],
             ['Moving average', f"Distance > {settings['moving_percent']}% from previous {settings['moving_window']} days; tested day excluded"],
             ['Grubbs', f"Two-sided alpha {settings['grubbs_alpha']}; up to {settings['grubbs_iterations']} pass(es)"],
             ['Enabled methods', ', '.join(METHODS[m] for m in settings['methods'])],
             ['Presentation', f"{settings['chart_type'].title()} chart; fitted polynomial degree {total['trend_degree']} (requested {settings['trend_degree']})"]]
    story += [table(rows, [43*mm, 131*mm]), Spacer(1, 4*mm)]
    for key in ['moving', 'grubbs', 'combination', 'caution']:
        story.append(para(result['methodology'][key], 'SmallReport'))
    story += [para('References: NIST/SEMATECH e-Handbook, Grubbs test (two-sided Student-t critical value); NumPy quantile, method=linear.', 'SmallReport')]
    for number, s in enumerate(result['series'], 1):
        story += [PageBreak(), para(f"03.{number:02d} / {s['name']}", 'Heading1'),
                  para('Output, selected-method flags and polynomial trend', 'SmallReport'), chart(result, s, height=80), Spacer(1, 4*mm)]
        story.append(table([['Mean / day', 'Std deviation', 'Median', 'IQR'],
                            [f(s['stats'][key]) for key in ['mean','std','median','iqr']]], [43.5*mm]*4))
        story += [Spacer(1, 4*mm), table([['Test', 'Flagged observations', 'Enabled']]+[
            [METHODS[m], len(s['flags'][m]), 'Yes' if m in settings['methods'] else 'No'] for m in METHODS], [72*mm, 60*mm, 42*mm]),
            Spacer(1, 4*mm), para(f"{len(s['anomalies'])} distinct flagged dates; {len(s['episodes'])} contiguous spike/drop episodes. Trend is an unconstrained least-squares fit and is not a forecast.", 'SmallReport'),
            para(f"IQR fences: {f(s['bounds']['iqr_lower'])} to {f(s['bounds']['iqr_upper'])} t/day.", 'SmallReport')]
    story += [PageBreak(), para('04 / Anomaly casebook', 'Heading1'),
              para('Every selected-method anomaly is listed below. Consecutive flagged days in the same direction are grouped into an episode; no points are omitted. Direction compares output with its prior-window mean, or the full-series mean during warm-up. Upward triangles mark spikes; downward triangles mark drops.', 'SmallReport')]
    local_charts=sum(len(s['episodes']) for s in result['series'])<=100
    if not local_charts:
        story.append(para('High-density casebook: all observations are listed; local episode charts are omitted above 100 episodes. The complete per-series charts appear in section 03.', 'SmallReport'))
    number = 0
    for s in result['series']:
        for episode in s['episodes']:
            number += 1
            points = episode['points']
            title = f"{number:03d} / {s['name']} / {episode['direction']} / {points[0]['date']}"
            if len(points) > 1:
                title += f" to {points[-1]['date']}"
            story.append(para(title, 'Heading2'))
            if local_charts:
                story.append(chart(result, s, max(0, points[0]['index']-5), min(len(source['dates']),points[-1]['index']+6), height=35))
            rows = [['Date', 'Output (t)', 'Baseline (t)', 'Z-score', 'MA distance', 'Triggered tests']]
            for p in points:
                distance = 'n/a' if p['moving_percent'] is None else f"{p['moving_percent']:.1f}%"
                rows.append([p['date'], f(p['value']), f(p['baseline']), f"{p['z_score']:.2f}", distance, ', '.join(METHODS[m] for m in p['tests'])])
            story += [table(rows, [26*mm, 25*mm, 25*mm, 20*mm, 25*mm, 53*mm]), Spacer(1, 6*mm)]
    if not number:
        story.append(para('No anomalies meet the enabled detection rules for this snapshot.'))
    def page(canvas, _):
        canvas.saveState()
        canvas.setFillColor(INK)
        canvas.rect(0, A4[1]-12*mm, A4[0], 12*mm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont('Helvetica-Bold', 8)
        canvas.drawString(18*mm, A4[1]-8*mm, 'WEYLAND-YUTANI  /  MINING OBSERVATORY')
        canvas.setFillColor(colors.HexColor('#6a7770'))
        canvas.setFont('Helvetica', 8)
        canvas.drawString(18*mm, 11*mm, f"Snapshot {source['snapshot']}  |  Tonnes / day")
        canvas.drawRightString(A4[0]-18*mm, 11*mm, str(doc.page))
        canvas.restoreState()
    doc.build(story, onFirstPage=page, onLaterPages=page)
    return out.getvalue()
