import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import time
import io
import os

# --- 嘗試載入 PDF 套件 ---
try:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
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
BOOK_MAP = {name: i+1 for i, name in enumerate(BIBLE_BOOKS)}
BOOK_FULL_MAP = {name: full for name, full in zip(BIBLE_BOOKS, FULL_BIBLE_BOOKS)}
SEPARATOR_LINE = "-" * 50  

# --- 讀取 GitHub 內的本機字型 ---
FONT_PATH = "NotoSansTC-Regular.ttf"
FONT_LOADED = False

if os.path.exists(FONT_PATH) and HAS_REPORTLAB:
    try:
        pdfmetrics.registerFont(TTFont('NotoSansTC', FONT_PATH))
        addMapping('NotoSansTC', 0, 0, 'NotoSansTC') # 正常
        addMapping('NotoSansTC', 1, 0, 'NotoSansTC') # 粗體
        addMapping('NotoSansTC', 0, 1, 'NotoSansTC') # 斜體
        addMapping('NotoSansTC', 1, 1, 'NotoSansTC') # 粗斜體
        FONT_LOADED = True
    except Exception:
        FONT_LOADED = False

# --- 核心邏輯函式 ---
def normalize_string(s):
    s = s.replace('啓', '啟')
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
            temp = "".join([str(cn_nums.get(c, 0)) for c in s])
            return int(temp)
        if s.startswith("十"): s = "一" + s
        parts = s.split("十")
        if len(parts) == 1: return cn_nums.get(parts[0], 0)
        elif len(parts) == 2:
            tens = cn_nums.get(parts[0], 0)
            if tens == 0: tens = 1
            units = cn_nums.get(parts[1], 0)
            return tens * 10 + units
    except: return 0
    return 0

def fetch_verse_dict(book_no, chapter):
    query = f"?VERSION=1&output[]=content&output[]=unit_code&output[]=segment_code&chapter_code={book_no}&section_code={chapter}&ORDER=id"
    url = f"https://www.recoveryversion.com.tw//api/getVerses{query}"
    verse_dict = {}
    try:
        headers = {
            'Accept': '*/*', 'Accept-Language': 'zh-TW,zh;q=0.9',
            'Origin': 'https://recoveryversion.twgbr.org', 'Referer': 'https://recoveryversion.twgbr.org/',
            'User-Agent': 'Mozilla/5.0'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status() 
        data = response.json()
        items = data if isinstance(data, list) else data.get('data', [])
        if not items and isinstance(data, dict):
            for key in data:
                if isinstance(data[key], list):
                    items = data[key]
                    break
        if not items: return {"error": "伺服器回傳空資料"}
        
        for item in items:
            v_val = item.get('segment_code')
            if v_val is None or str(v_val).strip() == '':
                v_val = item.get('unit_code', 0)
            try: v_num = int(v_val)
            except: v_num = 0
            content_html = item.get('content', '')
            if v_num > 0 and content_html:
                soup = BeautifulSoup(content_html, 'html.parser')
                for sup in soup.find_all('sup'): sup.decompose()
                for popup in soup.find_all('div', class_=lambda c: c and 'popup' in c): popup.decompose()
                verse_dict[v_num] = soup.get_text(separator='', strip=True)
        return verse_dict
    except Exception as e:
        return {"error": f"連線錯誤: {str(e)}"}

def parse_chapter_verse(text):
    match_mixed = re.match(r'^([一二三四五六七八九十]+)(\d+)$', text)
    if match_mixed: return cn_to_int(match_mixed.group(1)), int(match_mixed.group(2)), True
    match_split = re.split(r'[:\s]+', text)
    if len(match_split) >= 2: return cn_to_int(match_split[0]), cn_to_int(match_split[1]), True
    val_str = match_split[0]
    val = cn_to_int(val_str)
    if val_str.isdigit(): return None, val, False
    return val, 1, True

def parse_input_string(input_str):
    input_str = normalize_string(input_str)
    raw_items = re.split(r'[,，、\n]+', input_str)
    parsed_items = []
    last_book_no, last_book_name, last_chapter_val = None, "", None
    sorted_books = sorted(BIBLE_BOOKS, key=len, reverse=True)
    
    for item in raw_items:
        item = item.strip()
        if not item: continue
        curr_book_no, curr_book_name = None, ""
        remain = item
        for b in sorted_books:
            if remain.startswith(b):
                curr_book_name, curr_book_no = b, BOOK_MAP[b]
                remain = remain[len(b):].strip()
                break
        
        if curr_book_no is not None:
            last_book_no, last_book_name, last_chapter_val = curr_book_no, curr_book_name, None
        elif last_book_no is not None:
            curr_book_no, curr_book_name = last_book_no, last_book_name
        else: continue

        suffix = ""
        match_suffix = re.search(r'([上下ab])$', remain, re.IGNORECASE)
        if match_suffix:
            suffix = match_suffix.group(1)
            remain = remain[:-1].strip()

        range_parts = re.split(r'[~～-]', remain)
        main_part = range_parts[0].strip()
        end_part = range_parts[1].strip() if len(range_parts) > 1 else None
        
        p_ch, p_v, has_ch = parse_chapter_verse(main_part)
        chapter_start, verse_start = 1, 1
        
        if has_ch:
            chapter_start, verse_start = p_ch, p_v
            last_chapter_val = chapter_start
        else:
            if last_chapter_val is not None: chapter_start, verse_start = last_chapter_val, p_v
            else:
                chapter_start, verse_start = (p_ch if p_ch else p_v), 1
                last_chapter_val = chapter_start

        chapter_end, verse_end = chapter_start, verse_start
        if end_part:
            e_ch, e_v, e_has_ch = parse_chapter_verse(end_part)
            if e_has_ch:
                chapter_end, verse_end, last_chapter_val = e_ch, e_v, e_ch
            else:
                if e_v > 0: chapter_end, verse_end = chapter_start, e_v

        parsed_items.append({
            'name': curr_book_name, 'no': curr_book_no,
            'ch_start': chapter_start, 'v_start': verse_start,
            'ch_end': chapter_end, 'v_end': verse_end, 'suffix': suffix
        })
    return parsed_items

# --- 產生 網頁 (HTML) ---
def generate_html(text_content):
    html_template = """
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>經節抓取結果</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;700&display=swap');
            body { font-family: 'Noto Sans TC', sans-serif; line-height: 1.8; color: #333; max-width: 800px; margin: 0 auto; padding: 40px 20px; }
            .book-title { color: #1F4E79; font-size: 24px; font-weight: 700; margin-top: 30px; margin-bottom: 15px; border-bottom: 2px solid #1F4E79; padding-bottom: 5px; }
            .verse { font-size: 18px; margin-bottom: 12px; text-align: justify; }
            .verse strong { color: #B22222; margin-right: 8px; }
            .separator { text-align: center; margin: 40px 0; color: #ccc; letter-spacing: 5px; }
        </style>
    </head>
    <body>
    """
    for line in text_content.split('\n'):
        line = line.strip()
        if not line: continue
        elif line == SEPARATOR_LINE: html_template += '<div class="separator">✦ ✦ ✦</div>\n'
        elif line in FULL_BIBLE_BOOKS: html_template += f'<div class="book-title">{line}</div>\n'
        else:
            parts = line.split(" ", 1)
            if len(parts) == 2 and ":" in parts[0]: html_template += f'<div class="verse"><strong>{parts[0]}</strong>{parts[1]}</div>\n'
            else: html_template += f'<div class="verse">{line}</div>\n'
    html_template += "</body></html>"
    return html_template

# --- 產生 PDF ---
def generate_pdf(text_content):
    if not HAS_REPORTLAB or not FONT_LOADED: return None
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    verse_style = ParagraphStyle('VerseStyle', parent=styles['Normal'], fontName='NotoSansTC', fontSize=14, leading=22, wordWrap='CJK')
    title_style = ParagraphStyle('TitleStyle', parent=styles['Normal'], fontName='NotoSansTC', fontSize=16, leading=24, spaceAfter=10, textColor="#1F4E79")
    
    story = []
    for line in text_content.split('\n'):
        line = line.strip()
        if not line: story.append(Spacer(1, 10))
        elif line == SEPARATOR_LINE: story.append(Spacer(1, 15))
        elif line in FULL_BIBLE_BOOKS: story.append(Paragraph(f"<b>{line}</b>", title_style))
        else: story.append(Paragraph(line, verse_style))
            
    try:
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
    except Exception:
        return None

# --- 產生 圖片 (PNG) ---
def generate_image(text_content):
    if not HAS_PIL or not os.path.exists(FONT_PATH): return None
    font_size = 22
    line_spacing = 10
    margin = 40
    max_width = 800
    
    try: font = ImageFont.truetype(FONT_PATH, font_size)
    except Exception: return None 

    wrapped_lines = []
    for line in text_content.split('\n'):
        line = line.strip()
        if line == SEPARATOR_LINE:
            wrapped_lines.append("-" * 35) 
            continue
            
        current_line = ""
        for char in line:
            test_line = current_line + char
            try: text_len = font.getlength(test_line)
            except: text_len = font.getsize(test_line)[0] 
            
            if text_len > (max_width - 2 * margin):
                wrapped_lines.append(current_line)
                current_line = char
            else:
                current_line = test_line
        wrapped_lines.append(current_line)
        wrapped_lines.append("")

    total_height = 2 * margin + len(wrapped_lines) * (font_size + line_spacing)
    img = Image.new('RGB', (max_width, total_height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    y_text = margin
    for line in wrapped_lines:
        if line: 
            text_color = (31, 78, 121) if line in FULL_BIBLE_BOOKS else (0, 0, 0)
            draw.text((margin, y_text), line, font=font, fill=text_color)
        y_text += font_size + line_spacing
        
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


# --- Streamlit 介面邏輯 ---
st.set_page_config(page_title="恢復本經節抓取器", layout="centered")

# 如果找不到字型檔，在網頁最上方給予提示
if not os.path.exists(FONT_PATH):
    st.error("⚠️ 系統找不到 `NotoSansTC-Regular.ttf`！請確認您的 GitHub 專案根目錄下有這個檔案，且檔名大小寫完全一致。")

st.title("📖 恢復本經節抓取工具")

if "user_input" not in st.session_state:
    st.session_state.user_input = "可一1~5\n創一1~3"
if "final_text" not in st.session_state:
    st.session_state.final_text = ""

def clear_text():
    st.session_state.user_input = ""
    st.session_state.final_text = ""

st.text_area("請輸入經節 (可多行或逗號分隔)", key="user_input", height=150)

col1, col2 = st.columns([1, 4])
with col1: btn_start = st.button("🚀 開始抓取", type="primary")
with col2: st.button("🗑️ 清除內容", on_click=clear_text)

if btn_start:
    input_text = st.session_state.user_input
    if not input_text.strip():
        st.warning("請輸入內容！")
    else:
        st.info("正在透過 API 抓取中，請稍候...")
        progress_bar = st.progress(0)
        tasks = parse_input_string(input_text)
        
        final_lines = []
        current_book_no = None
        total_tasks = len(tasks)
        
        for i, t in enumerate(tasks):
            progress_bar.progress((i + 1) / total_tasks)
            
            for current_ch in range(t['ch_start'], t['ch_end'] + 1):
                verse_dict = fetch_verse_dict(t['no'], current_ch)
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
                                if current_book_no is not None:
                                    final_lines.append(SEPARATOR_LINE)
                                full_book_name = BOOK_FULL_MAP.get(t['name'], t['name'])
                                final_lines.append(full_book_name)
                                current_book_no = t['no']
                            
                            content = verse_dict[v]
                            final_lines.append(f"{t['name']} {current_ch}:{v} {content}")
                            
                    if not found_any:
                        final_lines.append(f"[{t['name']} {current_ch}:{start_v} 無此節]")
                time.sleep(0.1) 

        if not final_lines:
            st.error("找不到任何經文，請檢查輸入格式。")
        else:
            st.session_state.final_text = "\n".join(final_lines)

if st.session_state.final_text:
    final_text = st.session_state.final_text
    st.success("🎉 抓取完成！")
    st.subheader("抓取結果")
    st.code(final_text, language="text")
    
    st.write("### 📥 下載與匯出")
    
    # 建立 4 欄按鈕區：文字、網頁、PDF、圖片
    dl_col1, dl_col2, dl_col3, dl_col4 = st.columns(4)
    
    with dl_col1:
        st.download_button("📝 純文字 (.txt)", data=final_text, file_name="bible_verses.txt", mime="text/plain", use_container_width=True)
        
    with dl_col2:
        html_data = generate_html(final_text)
        st.download_button("🌐 網頁 (.html)", data=html_data, file_name="bible_verses.html", mime="text/html", use_container_width=True)
    
    with dl_col3:
        if HAS_REPORTLAB and FONT_LOADED:
            pdf_data = generate_pdf(final_text)
            if pdf_data:
                st.download_button("📄 PDF", data=pdf_data, file_name="bible_verses.pdf", mime="application/pdf", use_container_width=True)
            else:
                st.button("📄 PDF (錯誤)", disabled=True, use_container_width=True)
        else:
            st.button("📄 缺字型", disabled=True, use_container_width=True, help="請確認 GitHub 根目錄有 NotoSansTC-Regular.ttf")
            
    with dl_col4:
        if HAS_PIL and os.path.exists(FONT_PATH):
            img_data = generate_image(final_text)
            if img_data:
                st.download_button("🖼️ 圖片 (.png)", data=img_data, file_name="bible_verses.png", mime="image/png", use_container_width=True)
            else:
                st.button("🖼️ 圖片 (錯誤)", disabled=True, use_container_width=True)
        else:
            st.button("🖼️ 缺字型", disabled=True, use_container_width=True, help="請確認 GitHub 根目錄有 NotoSansTC-Regular.ttf")
