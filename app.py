import streamlit as st
import streamlit.components.v1 as components
import requests
from bs4 import BeautifulSoup
import re
import io
import os
import base64
import concurrent.futures

# --- 嘗試載入 PDF 套件 ---
try:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.platypus.flowables import HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.colors import HexColor
    from reportlab.lib.fonts import addMapping
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

# --- 嘗試載入 圖片 套件 ---
try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# --- 基礎設定 ---
BIBLE_BOOKS = [
    "創", "出", "利", "民", "申", "書", "士", "得", "撒上", "撒下", 
    "王上", "王下", "代上", "代下", "拉", "尼", "斯", "伯", "詩", "箴", 
    "傳", "歌", "賽", "耶", "哀", "結", "但", "何", "珥", "摩", 
    "俄", "拿", "彌", "鴻", "哈", "番", "該", "亞", "瑪",
    "太", "可", "路", "約", "徒", "羅", "林前", "林後", "加", "弗", 
    "腓", "西", "帖前", "帖後", "提前", "提後", "多", "門", "來", "雅", 
    "彼前", "彼後", "約壹", "約貳", "約參", "猶", "啟"
]
FULL_BIBLE_BOOKS = [
    "創世記", "出埃及記", "利未記", "民數記", "申命記", "約書亞記", "士師記", "路得記", "撒母耳記上", "撒母耳記下", 
    "列王紀上", "列王紀下", "歷代志上", "歷代志下", "以斯拉記", "尼希米記", "以斯帖記", "約伯記", "詩篇", "箴言", 
    "傳道書", "雅歌", "以賽亞書", "耶利米書", "耶利米哀歌", "以西結書", "但以理書", "何西阿書", "約珥書", "阿摩司書", 
    "俄巴底亞書", "約拿書", "彌迦書", "那鴻書", "哈巴谷書", "西番雅書", "哈該書", "撒迦利亞書", "瑪拉基書",
    "馬太福音", "馬可福音", "路加福音", "約翰福音", "使徒行傳", "羅馬書", "哥林多前書", "哥林多後書", "加拉太書", "以弗所書", 
    "腓立比書", "歌羅西書", "帖撒羅尼迦前書", "帖撒羅尼迦後書", "提摩太前書", "提摩太後書", "提多書", "腓利門書", "希伯來書", "雅各書", 
    "彼得前書", "彼得後書", "約翰一書", "約翰二書", "約翰三書", "猶大書", "啟示錄"
]

BOOK_ALIASES = {
    "羅馬": "羅", "創世": "創", "啟示": "啟", "約翰": "約", 
    "馬太": "太", "馬可": "可", "路加": "路", "哥前": "林前", 
    "哥後": "林後", "帖前": "帖前", "帖後": "帖後", "提前": "提前", 
    "提後": "提後", "彼前": "彼前", "彼後": "彼後"
}

BOOK_MAP = {name: i+1 for i, name in enumerate(BIBLE_BOOKS)}
BOOK_FULL_MAP = {name: full for name, full in zip(BIBLE_BOOKS, FULL_BIBLE_BOOKS)}
FULL_TO_SHORT = {full: short for short, full in zip(BIBLE_BOOKS, FULL_BIBLE_BOOKS)}
FULL_TO_SHORT.update(BOOK_ALIASES)
ALL_BOOK_NAMES = sorted(FULL_BIBLE_BOOKS + BIBLE_BOOKS + list(BOOK_ALIASES.keys()), key=len, reverse=True)

SEPARATOR_LINE = "-" * 50  
FOOTNOTE_SEPARATOR = "━━━━━━━━━━━━━━━━━━━━━━━━━━"
FOOTNOTE_TITLE = "【 註 解 】"

# --- Streamlit 介面邏輯 ---
st.set_page_config(page_title="恢復本經節抓取器", layout="centered", page_icon="📖")

st.markdown("""
    <style>
    label[data-testid="stWidgetLabel"] p { font-size: 18px !important; font-weight: bold !important; }
    div.stTextArea textarea { font-size: 20px !important; line-height: 1.6 !important; padding: 15px !important; height: 120px !important; }
    div[data-testid="InputInstructions"] { display: none !important; }
    .img-instruction { text-align:center; color:#B22222; font-weight:bold; margin-top:20px; margin-bottom:10px; font-size:16px;}
    </style>
    """, unsafe_allow_html=True)

FONT_PATH = "NotoSansTC-Regular.ttf"
FONT_LOADED = False

if not os.path.exists(FONT_PATH):
    st.error(f"⚠️ 系統找不到 `{FONT_PATH}`！請確認專案根目錄下有這個檔案。")
elif HAS_REPORTLAB:
    try:
        pdfmetrics.registerFont(TTFont('NotoSansTC', FONT_PATH))
        addMapping('NotoSansTC', 0, 0, 'NotoSansTC') 
        addMapping('NotoSansTC', 1, 0, 'NotoSansTC') 
        addMapping('NotoSansTC', 0, 1, 'NotoSansTC') 
        addMapping('NotoSansTC', 1, 1, 'NotoSansTC') 
        FONT_LOADED = True
    except Exception as e:
        st.error(f"⚠️ PDF 字型載入失敗，真實錯誤訊息：\n{str(e)}")

# --- 核心邏輯函式 ---
def normalize_string(s):
    s = s.replace('啓', '啟').replace('世紀', '世記')
    s = s.replace('/', ':').replace('／', ':').replace('\\', ':')
    s = s.replace('–', '~').replace('—', '~').replace('−', '~').replace('-', '~')
    r = ""
    for char in s:
        code = ord(char)
        if code == 12288: code = 32
        elif 65281 <= code <= 65374: code -= 65248
        r += chr(code)
    return r.strip()

def cn_to_int(s):
    if not s: return 0
    if s.isdigit(): return int(s)
    cn_nums = {'一':1, '二':2, '三':3, '四':4, '五':5, '六':6, '七':7, '八':8, '九':9, '十':10, '零':0}
    try:
        s = re.sub(r'[^\u4e00-\u9fa5]', '', s)
        if ('十' not in s) and (len(s) > 1):
            return int("".join([str(cn_nums.get(c, 0)) for c in s]))
        if s.startswith("十"): s = "一" + s
        parts = s.split("十")
        if len(parts) == 1: return cn_nums.get(parts[0], 0)
        elif len(parts) == 2:
            tens = cn_nums.get(parts[0], 0)
            if tens == 0: tens = 1
            return tens * 10 + cn_nums.get(parts[1], 0)
    except: return 0
    return 0

def parse_input_string(input_str):
    input_str = normalize_string(input_str)
    raw_items = re.split(r'[,，、。\n\t]+', input_str)
    parsed_items = []
    last_book_no, last_book_name, last_chapter_val = None, "", None
    
    for item in raw_items:
        item = item.strip()
        if not item: continue
        
        curr_book_no, curr_book_name = None, ""
        remain = item
        
        for b in ALL_BOOK_NAMES:
            if remain.startswith(b):
                short_name = FULL_TO_SHORT.get(b, b)
                curr_book_name, curr_book_no = short_name, BOOK_MAP[short_name]
                remain = remain[len(b):].strip()
                break
        
        if curr_book_no is not None:
            last_book_no, last_book_name, last_chapter_val = curr_book_no, curr_book_name, None
        elif last_book_no is not None:
            curr_book_no, curr_book_name = last_book_no, last_book_name
        else: continue

        remain = remain.replace('第', '').replace('節', '')
        remain = re.sub(r'[到至_]', '~', remain)
        remain = re.sub(r'([一二三四五六七八九十百零]+)(\d+)', r'\1 \2', remain)
        remain = re.sub(r'[一二三四五六七八九十百零]+', lambda m: str(cn_to_int(m.group(0))), remain)
        
        ch_str, v_str = "", ""
        if '章' in remain:
            parts = remain.split('章', 1)
            ch_str, v_str = parts[0].strip(), parts[1].strip()
        elif ':' in remain:
            parts = remain.split(':', 1)
            ch_str, v_str = parts[0].strip(), parts[1].strip()
        elif ' ' in remain.strip():
            parts = remain.strip().split(' ', 1)
            ch_str, v_str = parts[0].strip(), parts[1].strip()
        else:
            if last_chapter_val is not None: ch_str, v_str = str(last_chapter_val), remain.strip()
            else: ch_str, v_str = remain.strip(), ""
        
        current_ch = int(ch_str) if ch_str and ch_str.isdigit() else 1
        last_chapter_val = current_ch
        
        v_start, v_end = 1, 999
        ch_end = current_ch
        
        if v_str:
            if '~' in v_str:
                vs, ve = v_str.split('~', 1)
                vs, ve = vs.strip(), ve.strip()
                v_start = int(vs) if vs.isdigit() else 1
                
                if '章' in ve or ':' in ve or ' ' in ve:
                    if '章' in ve: ce_str, ve_str = ve.split('章', 1)
                    elif ':' in ve: ce_str, ve_str = ve.split(':', 1)
                    else: ce_str, ve_str = ve.split(' ', 1)
                    ch_end = int(ce_str.strip()) if ce_str.strip().isdigit() else current_ch
                    v_end = int(ve_str.strip()) if ve_str.strip().isdigit() else 999
                else:
                    v_end = int(ve) if ve.isdigit() else v_start
            else:
                v_start = int(v_str) if v_str.isdigit() else 1
                v_end = v_start
                
        parsed_items.append({
            'name': curr_book_name, 'no': curr_book_no,
            'ch_start': current_ch, 'v_start': v_start,
            'ch_end': ch_end, 'v_end': v_end
        })
    return parsed_items

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_footnotes_db(book_no, chapter):
    url = f"https://www.recoveryversion.com.tw/api/getFoots?VERSION=1&chapter_code={book_no}&section_code={chapter}"
    try:
        headers = {
            'Accept': '*/*', 'Origin': 'https://recoveryversion.twgbr.org', 
            'Referer': 'https://recoveryversion.twgbr.org/', 'User-Agent': 'Mozilla/5.0'
        }
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            fn_dict = {}
            for item in data:
                v_num, n_num, content = item.get("segment_code", 0), item.get("note_num", 0), item.get("note_content", "")
                if v_num > 0 and content:
                    if v_num not in fn_dict: fn_dict[v_num] = {}
                    content = content.replace('<br>', ' ').replace('<br/>', ' ').replace('ˍ', ' ')
                    fn_dict[v_num][str(n_num)] = re.sub(r'<[^>]+>', '', content)
            return fn_dict
    except Exception: pass
    return {}

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_verse_dict(book_no, chapter, include_footnotes):
    query = f"?VERSION=1&output[]=content&output[]=unit_code&output[]=segment_code&chapter_code={book_no}&section_code={chapter}&ORDER=id"
    url = f"https://www.recoveryversion.com.tw/api/getVerses{query}"
    fn_db = fetch_footnotes_db(book_no, chapter) if include_footnotes else {}
    if fn_db and "error" in fn_db: return {"error": f"註解抓取異常: {fn_db['error']}"}

    try:
        headers = {
            'Accept': '*/*', 'Origin': 'https://recoveryversion.twgbr.org', 
            'Referer': 'https://recoveryversion.twgbr.org/', 'User-Agent': 'Mozilla/5.0'
        }
        response = requests.get(url, headers=headers, timeout=15)
        data = response.json()
        items = data if isinstance(data, list) else data.get('data', [])
        if not items and isinstance(data, dict):
            for key in data:
                if isinstance(data[key], list):
                    items = data[key]; break
        if not items: return {"error": "伺服器回傳空資料"}
        
        verse_dict = {}
        for item in items:
            v_val = item.get('segment_code') or item.get('unit_code', 0)
            try: v_num = int(v_val)
            except: v_num = 0
            
            content_html = item.get('content', '')
            if v_num > 0 and content_html:
                soup = BeautifulSoup(content_html, 'html.parser')
                paired_footnotes = []
                if include_footnotes:
                    for popup in soup.find_all('div', class_=lambda c: c and 'popup' in c): popup.decompose()
                    if v_num in fn_db:
                        for n_num in sorted(fn_db[v_num].keys(), key=lambda x: int(x) if x.isdigit() else 0):
                            paired_footnotes.append(f"[註{n_num}] {fn_db[v_num][n_num]}")
                    for sup in soup.find_all('sup'): sup.replace_with(f"[{sup.get_text(strip=True)}]") 
                    for a_note in soup.find_all('a', class_=lambda c: c and 'note' in c.lower()): a_note.replace_with(f"[{a_note.get_text(strip=True)}]")
                else:
                    for sup in soup.find_all('sup'): sup.decompose()
                    for popup in soup.find_all('div', class_=lambda c: c and 'popup' in c): popup.decompose()
                verse_dict[v_num] = {'text': soup.get_text(separator='', strip=True), 'footnotes': paired_footnotes}
        return verse_dict
    except Exception as e: return {"error": f"連線錯誤: {str(e)}"}

# --- 產生 超大按鈕複製元件 ---
def render_giant_copy_button(text_content):
    b64_text = base64.b64encode(text_content.encode('utf-8')).decode('utf-8')
    html_code = f"""
    <button onclick="copyToClipboard()" style="width:100%; padding:15px; font-size:22px; font-weight:bold; font-family:sans-serif; background-color:#FF4B4B; color:white; border:none; border-radius:8px; cursor:pointer; box-shadow: 0 4px 6px rgba(0,0,0,0.1); transition: 0.2s;">
        📋 一鍵複製全文 (可貼至LINE)
    </button>
    <script>
    function copyToClipboard() {{
        const str = decodeURIComponent(escape(window.atob('{b64_text}')));
        navigator.clipboard.writeText(str).then(function() {{
            alert('✅ 複製成功！\\n您可以直接去 LINE 或 Word 貼上了！');
        }}, function(err) {{
            alert('❌ 複製失敗，請手動複製。');
        }});
    }}
    </script>
    """
    components.html(html_code, height=75)

# --- 產生 網頁版 HTML ---
def generate_html(text_content, font_mult, theme):
    is_dark = (theme == "dark")
    bg_col = "#1E1E1E" if is_dark else "#ffffff"
    text_col = "#E6E6E6" if is_dark else "#333333"
    title_col = "#87CEFA" if is_dark else "#1F4E79"
    num_col = "#FF7F7F" if is_dark else "#B22222"
    fn_col = "#969696" if is_dark else "#555555"
    sep_col = "#888888" if is_dark else "#CCCCCC"
    
    base_size = int(18 * font_mult)
    title_size = int(24 * font_mult)
    fn_size = int(15 * font_mult)

    html_template = f"""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;700&display=swap');
            body {{ font-family: 'Noto Sans TC', sans-serif; line-height: 1.8; color: {text_col}; max-width: 800px; margin: 0 auto; padding: 20px; background-color: {bg_col}; }}
            .book-title {{ color: {title_col}; font-size: {title_size}px; font-weight: 700; margin-top: 40px; margin-bottom: 20px; padding-bottom: 10px; border-bottom: 2px solid {title_col}; }}
            .verse, .footnote {{ display: flex; text-align: justify; margin-bottom: 12px; }}
            .verse {{ font-size: {base_size}px; }}
            .verse .ref {{ flex-shrink: 0; margin-right: 6px; color: {num_col}; font-weight: bold; }}
            .verse .ref-book {{ color: {title_col}; }}
            .footnote-title {{ font-size: {int(20*font_mult)}px; font-weight: bold; color: {title_col}; text-align: center; margin-top: 50px; margin-bottom: 20px; }}
            .footnote {{ font-size: {fn_size}px; color: {fn_col}; }}
            .footnote .ref {{ flex-shrink: 0; margin-right: 8px; color: {fn_col}; font-weight: bold; }}
            .separator {{ text-align: center; margin: 40px 0; color: {sep_col}; letter-spacing: 5px; font-size: {int(14*font_mult)}px;}}
        </style>
    </head>
    <body>
    """
    for line in text_content.split('\n'):
        line = line.strip()
        if not line: continue
        elif line == SEPARATOR_LINE: html_template += '<div class="separator">◆ &nbsp; ◆ &nbsp; ◆</div>\n'
        elif line == FOOTNOTE_SEPARATOR: html_template += '<div class="separator">━━━━━━━━━━</div>\n'
        elif line == FOOTNOTE_TITLE: html_template += f'<div class="footnote-title">{line}</div>\n'
        elif line in FULL_BIBLE_BOOKS: html_template += f'<div class="book-title">{line}</div>\n'
        else:
            match = re.match(r'^(([一-龥]*)\s*(\d+:\d+(?:\s*｜\s*\[[^\]]+\])?))\s+(.*)', line)
            if match:
                full_ref, book_part, num_part, text = match.group(1), match.group(2), match.group(3), match.group(4)
                if "｜" in full_ref:
                    html_template += f'<div class="footnote"><span class="ref">{full_ref}</span><span class="text">{text}</span></div>\n'
                else:
                    html_template += f'<div class="verse"><span class="ref"><span class="ref-book">{book_part} </span>{num_part}</span><span class="text">{text}</span></div>\n'
            else:
                html_template += f'<div class="verse">{line}</div>\n'
    html_template += "</body></html>"
    return html_template


# --- 產生 PDF ---
def generate_pdf(text_content, font_mult, theme):
    if not HAS_REPORTLAB or not FONT_LOADED: return None
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    
    is_dark = (theme == "dark")
    c_text = "#E6E6E6" if is_dark else "#282828"
    c_title = "#87CEFA" if is_dark else "#1F4E79"
    c_num = "#FF7F7F" if is_dark else "#B22222"
    c_fn = "#969696" if is_dark else "#555555"
    c_bg = HexColor("#1E1E1E") if is_dark else HexColor("#FFFFFF")
    
    verse_style = ParagraphStyle('VerseStyle', fontName='NotoSansTC', fontSize=14*font_mult, leading=22*font_mult, wordWrap='CJK', textColor=HexColor(c_text))
    footnote_style = ParagraphStyle('FootnoteStyle', fontName='NotoSansTC', fontSize=11*font_mult, leading=17*font_mult, textColor=HexColor(c_fn), wordWrap='CJK')
    title_style = ParagraphStyle('TitleStyle', fontName='NotoSansTC', fontSize=16*font_mult, leading=24*font_mult, spaceBefore=20, spaceAfter=8, textColor=HexColor(c_title))
    separator_style = ParagraphStyle('SeparatorStyle', fontName='NotoSansTC', fontSize=12*font_mult, alignment=TA_CENTER, textColor=HexColor("#888888" if is_dark else "#CCCCCC"), spaceBefore=15, spaceAfter=15)
    
    left_col_width = 75 * font_mult
    right_col_width = 495 - left_col_width

    story = []
    for line in text_content.split('\n'):
        line = line.strip()
        if not line: continue
        elif line == SEPARATOR_LINE: story.append(Paragraph("◆ &nbsp; ◆ &nbsp; ◆", separator_style))
        elif line == FOOTNOTE_SEPARATOR: story.append(Spacer(1, 20))
        elif line == FOOTNOTE_TITLE: story.append(Paragraph(line, title_style))
        elif line in FULL_BIBLE_BOOKS: 
            story.append(Paragraph(line, title_style))
            story.append(HRFlowable(width=495, thickness=1.5, color=HexColor(c_title), spaceBefore=0, spaceAfter=15))
        elif "｜" in line: 
            parts = line.split(" ｜ ", 1)
            if len(parts) == 2:
                p_left = Paragraph(f'<font color="{c_fn}"><b>{parts[0]}</b></font>', footnote_style)
                p_right = Paragraph(parts[1], footnote_style)
                t = Table([[p_left, p_right]], colWidths=[left_col_width, right_col_width])
                t.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('PADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 6)]))
                story.append(t)
            else:
                story.append(Paragraph(line, footnote_style))
        else:
            match = re.match(r'^(([一-龥]*)\s*(\d+:\d+))\s+(.*)', line)
            if match:
                book_part, num_part, text_part = match.group(2).strip(), match.group(3).strip(), match.group(4).strip()
                color_str = ""
                if book_part: color_str += f'<font color="{c_title}">{book_part}</font> '
                if num_part: color_str += f'<font color="{c_num}">{num_part}</font>'
                p_left = Paragraph(color_str, verse_style)
                p_right = Paragraph(text_part, verse_style)
                t = Table([[p_left, p_right]], colWidths=[left_col_width, right_col_width])
                t.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('PADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 10)]))
                story.append(t)
            else:
                story.append(Paragraph(line, verse_style))
                
    def paint_bg(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(c_bg)
        canvas.rect(0, 0, A4[0], A4[1], fill=1)
        canvas.restoreState()

    try:
        doc.build(story, onFirstPage=paint_bg, onLaterPages=paint_bg)
        buffer.seek(0)
        return buffer.getvalue()
    except Exception: return None

# --- 產生圖片 ---
def generate_image(text_content, font_mult, theme):
    if not HAS_PIL or not os.path.exists(FONT_PATH): return None
    
    is_dark = (theme == "dark")
    c_bg = (30, 30, 30) if is_dark else (255, 255, 255)
    c_text = (235, 235, 235) if is_dark else (40, 40, 40)
    c_title = (135, 206, 250) if is_dark else (31, 78, 121)
    c_num = (255, 127, 127) if is_dark else (178, 34, 34)
    c_fn = (150, 150, 150) if is_dark else (100, 100, 100)
    c_sep = (100, 100, 100) if is_dark else (200, 200, 200)

    SCALE = 3 
    font_size = int(20 * SCALE * font_mult)
    margin = 40 * SCALE 
    max_width = 800 * SCALE
    usable_width = max_width - 2 * margin - (30 * SCALE)
    
    intra_verse_spacing = int(font_size * 0.2) 
    inter_verse_spacing = int(font_size * 0.8) 
    
    try: 
        font = ImageFont.truetype(FONT_PATH, font_size)
        font_small = ImageFont.truetype(FONT_PATH, int(font_size * 0.8))
        font_title = ImageFont.truetype(FONT_PATH, int(font_size * 1.3))
    except Exception: return None 

    wrapped_lines = [] 
    for line in text_content.split('\n'):
        line = line.strip()
        if not line: continue
        if line == FOOTNOTE_SEPARATOR:
            wrapped_lines.extend([("_SPACER_",0,"spacer",None), ("━━━━━━━━━━━━━",0,"spacer",None), ("_SPACER_",0,"spacer",None)])
            continue
        if line == FOOTNOTE_TITLE or line in FULL_BIBLE_BOOKS:
            wrapped_lines.extend([("_SPACER_",0,"spacer",None), (line,0,"title",None), ("_LINE_",0,"line",None)])
            continue
        if line == SEPARATOR_LINE:
            wrapped_lines.extend([("_SPACER_",0,"spacer",None), ("◆   ◆   ◆",0,"separator",None), ("_SPACER_",0,"spacer",None)])
            continue
            
        is_footnote = "｜" in line
        current_font = font_small if is_footnote else font
        book_part, num_part = "", ""
        indent_width = 0
        
        match = re.match(r'^(([一-龥]*)\s*(\d+:\d+(?:\s*｜\s*\[[^\]]+\])?))\s+(.*)', line)
        if match:
            prefix, book_part, num_part, line = match.group(1), match.group(2).strip(), match.group(3).strip(), match.group(4).strip()
            # ★ 修復：精算實際要印出來的前綴文字寬度
            actual_prefix = ""
            if book_part: actual_prefix += book_part + " "
            if num_part: actual_prefix += num_part + " "
            try: indent_width = current_font.getlength(actual_prefix)
            except: indent_width = current_font.getsize(actual_prefix)[0]
            
        current_line, is_first_line = "", True
        
        # ★ 修復：強制扣除前綴寬度，保證不超出畫布
        current_max_width = max(usable_width - indent_width, int(font_size * 2))
        
        for char in line:
            test_line = current_line + char
            try: text_len = current_font.getlength(test_line)
            except: text_len = current_font.getsize(test_line)[0] 
            
            if text_len > current_max_width:
                wrapped_lines.append((current_line, 0 if is_first_line else indent_width, "footnote" if is_footnote else "verse", (book_part, num_part) if is_first_line else None))
                is_first_line = False
                current_line = char
            else:
                current_line = test_line
                
        if current_line:
            wrapped_lines.append((current_line, 0 if is_first_line else indent_width, "footnote" if is_footnote else "verse", (book_part, num_part) if is_first_line else None))
        wrapped_lines.append(("_VERSE_SPACER_", 0, "spacer", None)) 

    total_height = 2 * margin
    for text, _, l_type, _ in wrapped_lines:
        if l_type == "title": total_height += int(font_size * 2.0)
        elif l_type == "line": total_height += int(font_size * 0.8) 
        elif l_type == "separator": total_height += int(font_size * 1.2)
        elif text == "_SPACER_": total_height += int(font_size * 0.5) 
        elif text == "_VERSE_SPACER_": total_height += inter_verse_spacing 
        elif l_type == "footnote": total_height += int(font_size * 0.8) + intra_verse_spacing
        else: total_height += font_size + intra_verse_spacing 
    total_height += (100 * SCALE) 
            
    img = Image.new('RGB', (max_width, total_height), color=c_bg)
    draw = ImageDraw.Draw(img)
    
    y_text = margin
    for text, x_offset, l_type, prefix_data in wrapped_lines:
        if text == "_SPACER_": y_text += int(font_size * 0.5)
        elif text == "_VERSE_SPACER_": y_text += inter_verse_spacing
        elif l_type == "title":
            bbox = draw.textbbox((margin, y_text), text, font=font_title)
            draw.text((margin, y_text), text, font=font_title, fill=c_title)
            y_text = bbox[3] + int(8 * SCALE)
        elif l_type == "line":
            draw.line([(margin, y_text), (max_width - margin, y_text)], fill=c_title, width=int(2.5*SCALE))
            y_text += int(15 * SCALE) 
        elif l_type == "separator":
            try: w = font.getlength(text)
            except: w = font.getsize(text)[0]
            draw.text(((max_width - w) / 2, y_text), text, font=font, fill=c_sep)
            y_text += int(font_size * 1.2)
        elif "verse" in l_type or l_type == "footnote":
            is_footnote_line = (l_type == "footnote")
            current_font = font_small if is_footnote_line else font
            if prefix_data: 
                bp, np = prefix_data
                cur_x = margin
                if bp: 
                    draw.text((cur_x, y_text), bp + " ", font=current_font, fill=c_fn if is_footnote_line else c_title)
                    try: w = current_font.getlength(bp + " ")
                    except: w = current_font.getsize(bp + " ")[0]
                    cur_x += w
                if np: 
                    draw.text((cur_x, y_text), np + " ", font=current_font, fill=c_fn if is_footnote_line else c_num)
                    try: w = current_font.getlength(np + " ")
                    except: w = current_font.getsize(np + " ")[0]
                    cur_x += w
                draw.text((cur_x, y_text), text, font=current_font, fill=c_fn if is_footnote_line else c_text)
            else:
                draw.text((margin + x_offset, y_text), text, font=current_font, fill=c_fn if is_footnote_line else c_text)
            y_text += (int(font_size * 0.8) if is_footnote_line else font_size) + intra_verse_spacing
            
    if total_height > 20000: SCALE_DOWN = 2
    else: SCALE_DOWN = SCALE
        
    img = img.resize((max_width // SCALE_DOWN, total_height // SCALE_DOWN), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()

# --- Streamlit 介面 ---
st.title("📖 恢復本經節抓取工具")

if "user_input" not in st.session_state:
    st.session_state.user_input = st.query_params.get("q", "")
if "final_text" not in st.session_state:
    st.session_state.final_text = ""
if "show_web" not in st.session_state:
    st.session_state.show_web = False 

auto_trigger = False
if "q" in st.query_params and not st.session_state.get("auto_triggered", False):
    st.session_state.auto_triggered = True
    auto_trigger = True

def clear_text():
    st.session_state.user_input = ""
    st.session_state.final_text = ""
    st.session_state.show_web = False
    st.query_params.clear()

with st.expander("⚙️ 輸出與排版設定 (深色模式/大小)", expanded=True):
    col_a, col_b = st.columns(2)
    with col_a:
        output_mode = st.radio("排版模式：", ["模式 1：每節顯示書名簡寫 (例如：可 1:1)", "模式 2：頂部顯示完整書名 (例如：馬可福音)"], index=1)
        theme_setting = st.radio("配色主題 (適用圖片、PDF與網頁)：", ["light (經典白底)", "dark (護眼深色)"], index=0)
    with col_b:
        font_size_setting = st.radio("輸出字體大小：", ["標準", "偏大", "特大 (長輩友善)"], index=0)
        include_footnotes = st.checkbox("📖 包含註解 (附加於最下方)", value=False)

st.markdown("### 🎙️ 請用語音或鍵盤輸入經節")
user_input = st.text_area("", key="user_input", placeholder="例如：約三15-16，羅馬10/17，加5/6")

col1, col2 = st.columns([1, 4])
with col1: btn_start = st.button("🚀 開始抓取", type="primary")
with col2: st.button("🗑️ 清除內容", on_click=clear_text)

if btn_start or auto_trigger:
    st.session_state.show_web = False 
    if not user_input.strip():
        st.warning("請輸入內容！")
    else:
        st.query_params["q"] = user_input
        st.success("🔗 網址已更新！您可以直接複製瀏覽器上方網址，傳給朋友點開會自動抓取！")
        
        tasks = parse_input_string(user_input)
        unique_fetches = set()
        for t in tasks:
            if t['ch_start'] > t['ch_end']: t['ch_end'] = t['ch_start']
            for current_ch in range(t['ch_start'], t['ch_end'] + 1):
                unique_fetches.add((t['no'], current_ch))
        
        if len(unique_fetches) > 40:
            st.error("⚠️ 一次查詢的章節數量過多（超過 40 章）。為了保護伺服器，請分批查詢！")
            st.stop()

        st.info(f"⚡ 正在並行抓取 {len(unique_fetches)} 個章節中，請稍候...")
        progress_bar = st.progress(0)
        
        results_map = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_req = {executor.submit(fetch_verse_dict, req[0], req[1], include_footnotes): req for req in unique_fetches}
            for i, future in enumerate(concurrent.futures.as_completed(future_to_req)):
                req = future_to_req[future]  
                results_map[req] = future.result() 
                progress_bar.progress((i + 1) / len(unique_fetches))

        final_lines, all_footnotes_list, current_book_no = [], [], None
        for t in tasks:
            for current_ch in range(t['ch_start'], t['ch_end'] + 1):
                verse_dict = results_map.get((t['no'], current_ch), {})
                if verse_dict and "error" in verse_dict:
                    st.error(f"抓取 {t['name']} {current_ch} 章時發生錯誤: {verse_dict['error']}")
                    continue
                if verse_dict:
                    start_v = t['v_start'] if current_ch == t['ch_start'] else 1
                    end_v = t['v_end'] if current_ch == t['ch_end'] else 999
                    found_any = False
                    for v in sorted(verse_dict.keys()):
                        if start_v <= v <= end_v:
                            found_any = True
                            if t['no'] != current_book_no:
                                if current_book_no is not None: final_lines.append(SEPARATOR_LINE)
                                if output_mode.startswith("模式 2"): final_lines.append(BOOK_FULL_MAP.get(t['name'], t['name']))
                                current_book_no = t['no']
                            content = verse_dict[v]['text']
                            prefix = f"{t['name']} {current_ch}:{v}" if output_mode.startswith("模式 1") else f"{current_ch}:{v}"
                            final_lines.append(f"{prefix} {content}")
                            if include_footnotes and verse_dict[v]['footnotes']:
                                for fn_text in verse_dict[v]['footnotes']: all_footnotes_list.append(f"{prefix} ｜ {fn_text}")
                    if not found_any: final_lines.append(f"[{t['name']} {current_ch}:{start_v} 無此節]")

        if include_footnotes and all_footnotes_list:
            final_lines.extend([FOOTNOTE_SEPARATOR, FOOTNOTE_TITLE] + all_footnotes_list)

        if not final_lines: st.error("找不到任何經文，請檢查您的輸入是否正確。")
        else: st.session_state.final_text = "\n".join(final_lines)

if st.session_state.final_text:
    final_text = st.session_state.final_text
    st.success("🎉 抓取完成！")
    
    render_giant_copy_button(final_text)
    
    with st.container(height=350): st.code(final_text, language="text")
    
    font_mult = {"標準": 1.0, "偏大": 1.25, "特大 (長輩友善)": 1.5}[font_size_setting]
    theme_val = "dark" if theme_setting.startswith("dark") else "light"
    
    st.write("### 📥 分享與匯出 (圖片 / PDF / 網頁版)")
    st.markdown('<div class="img-instruction">💡 若在 LINE 裡無法長按圖片，請直接點擊下方「📥 下載圖片」按鈕！</div>', unsafe_allow_html=True)
    
    img_data = generate_image(final_text, font_mult, theme_val) if HAS_PIL else None
    
    dl_col1, dl_col2, dl_col3, dl_col4 = st.columns(4)
    with dl_col1:
        if img_data: st.download_button("📥 下載圖片", data=img_data, file_name="bible_verses.png", mime="image/png", use_container_width=True, type="primary")
        else: st.button("🖼️ 缺圖片套件", disabled=True, use_container_width=True)
    with dl_col2:
        if st.button("🌐 展開網頁版", use_container_width=True):
            st.session_state.show_web = not st.session_state.show_web
    with dl_col3: 
        st.download_button("📝 下載純文字", data=final_text, file_name="bible_verses.txt", mime="text/plain", use_container_width=True)
    with dl_col4:
        if HAS_REPORTLAB and FONT_LOADED:
            pdf_data = generate_pdf(final_text, font_mult, theme_val)
            if pdf_data: st.download_button("📄 下載 PDF", data=pdf_data, file_name="bible_verses.pdf", mime="application/pdf", use_container_width=True)
            else: st.button("📄 PDF (錯誤)", disabled=True, use_container_width=True)
        else: st.button("📄 缺字型", disabled=True, use_container_width=True)

    if st.session_state.show_web:
        st.markdown("---")
        st.markdown("### 🌐 網頁版預覽 (可直接在此滑動閱讀)")
        html_data = generate_html(final_text, font_mult, theme_val)
        components.html(html_data, height=650, scrolling=True)

    st.write("---")
    if img_data:
        b64_img = base64.b64encode(img_data).decode('utf-8')
        st.markdown(f'<img src="data:image/png;base64,{b64_img}" style="width: 100%; border: 1px solid #ccc; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); -webkit-touch-callout: default; pointer-events: auto;">', unsafe_allow_html=True)
