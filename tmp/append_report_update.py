from io import BytesIO
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from pypdf import PdfReader, PdfWriter
from xml.sax.saxutils import escape

root = Path(r'\\wsl.localhost\Ubuntu\home\oaa\alfa-hack-2026')
out = root / 'output/pdf/alfa-hack-final-report.pdf'
pdfmetrics.registerFont(TTFont('Arial', r'C:\Windows\Fonts\arial.ttf'))
pdfmetrics.registerFont(TTFont('Arial-Bold', r'C:\Windows\Fonts\arialbd.ttf'))
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='TitleRU', fontName='Arial-Bold', fontSize=21, leading=26, textColor=colors.HexColor('#17395e'), spaceAfter=8))
styles.add(ParagraphStyle(name='SubRU', fontName='Arial', fontSize=10, leading=14, textColor=colors.HexColor('#506783'), spaceAfter=12))
styles.add(ParagraphStyle(name='HeadRU', fontName='Arial-Bold', fontSize=12, leading=15, textColor=colors.HexColor('#17395e'), spaceBefore=8, spaceAfter=4, keepWithNext=True))
styles.add(ParagraphStyle(name='BodyRU', fontName='Arial', fontSize=9.3, leading=13, textColor=colors.HexColor('#253247'), spaceAfter=5))
styles.add(ParagraphStyle(name='SmallRU', fontName='Arial', fontSize=8, leading=11, textColor=colors.HexColor('#53657d')))

def P(s, style='BodyRU'):
    return Paragraph(s, styles[style])

def footer(canvas, doc):
    canvas.saveState()
    w, h = A4
    canvas.setStrokeColor(colors.HexColor('#d5deea'))
    canvas.line(20*mm, 15*mm, w-20*mm, 15*mm)
    canvas.setFont('Arial', 7.5)
    canvas.setFillColor(colors.HexColor('#64758b'))
    canvas.drawString(20*mm, 10*mm, 'ALFRED · Актуализация реализации')
    canvas.drawRightString(w-20*mm, 10*mm, f'{doc.page}')
    canvas.restoreState()

buf = BytesIO()
doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm, topMargin=18*mm, bottomMargin=22*mm, title='Актуализация — одновызовный анализ')
story = [P('Актуализация реализации', 'TitleRU'), P('Состояние на 26 октября 2026 года · дополнение к отчёту на страницах 2–3', 'SubRU')]
story.append(P('Активный путь анализа', 'HeadRU'))
story.append(P('Go worker передаёт один запрос в RouterAI: профиль компании, аналоги, новость, вопрос пользователя и отобранные банковские выдержки. В system prompt задана JSON-структура из шести полей: <b>bank_view</b>, <b>ai_analysis</b>, <b>risks</b>, <b>opportunities</b>, <b>solutions</b> и <b>source_ids</b>.', 'BodyRU'))
story.append(P('Go проверяет обязательные поля, массивы и каждый ID источника, собирает ссылки для UI и сохраняет trace. Для активного запроса передаются <b>max_tokens=32000</b> и <b>reasoning.effort=low</b>. Исходный таймаут оставлен равным 50 секундам.', 'BodyRU'))
story.append(P('Прежний многовызовный сценарий с планом, ответом и отдельной проверкой сохранён в <code>generateAnalysisWithExperts</code>, но отключён через <code>expertAnalysisWorkflowEnabled = false</code>. Описание этого сценария на страницах 2–3 выше заменяется текущим дополнением.', 'BodyRU'))
story.append(P('Проверка в приложении', 'HeadRU'))
rows = [
    [P('<b>Шаг</b>', 'SmallRU'), P('<b>Результат</b>', 'SmallRU')],
    [P('Сборка и запуск worker', 'BodyRU'), P('Go worker собран и перезапущен через Compose.', 'BodyRU')],
    [P('Короткий запрос RouterAI', 'BodyRU'), P('HTTP 200; модель разрешилась как <code>z-ai/glm-5.3-flash</code>; ответ <code>OK</code>, finish_reason=stop.', 'BodyRU')],
    [P('Анализ из очереди', 'BodyRU'), P('Задача завершилась со статусом complete, provenance=approved-llm; trace подтверждает один структурированный вызов и четыре цитаты.', 'BodyRU')],
    [P('Маршрутизация и лимиты приложения', 'BodyRU'), P('Wi-Fi proxy удалён. Запросы идут стандартным сетевым путём. Внутреннего лимита числа вызовов или бюджета LLM нет.', 'BodyRU')],
]
t = Table(rows, colWidths=[54*mm, 112*mm], repeatRows=1, hAlign='LEFT')
t.setStyle(TableStyle([
    ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eaf0f7')),
    ('BOX',(0,0),(-1,-1),0.5,colors.HexColor('#cbd6e3')),
    ('INNERGRID',(0,0),(-1,-1),0.35,colors.HexColor('#cbd6e3')),
    ('VALIGN',(0,0),(-1,-1),'TOP'),
    ('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),
    ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
]))
story += [t, Spacer(1, 5*mm), P('Это дополнение фиксирует одновызовную реализацию и фактическую проверку. Оно не меняет остальные данные, критерии и ограничения решения, перечисленные в основном отчёте.', 'SmallRU')]
doc.build(story, onFirstPage=footer, onLaterPages=footer)

base = PdfReader(str(out))
update = PdfReader(BytesIO(buf.getvalue()))
writer = PdfWriter()
for page in base.pages:
    writer.add_page(page)
for page in update.pages:
    writer.add_page(page)
writer.add_metadata({'/Title': 'ALFRED — отчёт о решении и актуализация', '/Author': 'Команда ALFRED'})
with out.open('wb') as f:
    writer.write(f)
print(f'pages={len(writer.pages)} size={out.stat().st_size}')