import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import time
import io
import os

# --- 嘗試載入 PDF 與圖片套件 ---
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

ALL_BOOK_NAMES = sorted(FULL_BIBLE_BOOKS + BIBLE_BOOKS, key=len, reverse=True)
FULL_TO_SHORT = {full: short for short, full in zip(BIBLE_BOOKS, FULL_BIBLE_BOOKS)}

SEPARATOR_LINE = "-" * 50  
FOOTNOTE_SEPARATOR = "━━━━━━━━━━━━━━━━━━━━━━━━━━"
FOOTNOTE_TITLE = "【 註 解 】"

FONT_PATH = "NotoSansTC-VariableFont_wght.ttf"
FONT_LOADED = False

if os.path.exists(FONT_PATH) and HAS_REPORTLAB:
    try:
        pdfmetrics.registerFont(TTFont('NotoSansTC', FONT_PATH))
        addMapping('NotoSansTC', 0, 0, 'NotoSansTC') 
        addMapping('NotoSansTC', 1, 0, 'NotoSansTC') 
        addMapping('NotoSansTC', 0, 1, 'NotoSansTC') 
        addMapping('NotoSansTC', 1, 1, 'NotoSansTC') 
        FONT_LOADED = True
    except Exception:
        pass

# --- 核心邏輯函式 ---
def normalize_string(s):
    s = s.replace('啓', '啟').replace('世紀', '世記')
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
        remain = re.sub(r'[到至－—_~～-]', '~', remain)
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
            if last_chapter_val is not None:
                ch_str, v_str = str(last_chapter_val), remain.strip()
            else:
                ch_str, v_str = remain.strip(), ""
        
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

# --- API 抓取函式 ---
def fetch_footnotes_db(book_no, chapter):
    url = f"https://www.recoveryversion.com.tw/api/getFoots?VERSION=1&chapter_code={book_no}&section_code={chapter}"
    try:
        headers = {
            'Accept': '*/*',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Origin': 'https://recoveryversion.twgbr.org',
            'Referer': 'https://recoveryversion.twgbr.org/',
            'User-Agent': 'Mozilla/5.0'
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
    except: pass
    return {}

def fetch_verse_dict(book_no, chapter, include_footnotes=False):
    query = f"?VERSION=1&output[]=content&output[]=unit_code&output[]=segment_code&chapter_code={book_no}&section_code={chapter}&ORDER=id"
    url = f"https://www.recoveryversion.com.tw/api/getVerses{query}"
    fn_db = fetch_footnotes_db(book_no, chapter) if include_footnotes else {}
    
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
                    for sup in soup.find_all('sup'):
                        sup.replace_with(f"[{sup.get_text(strip=True)}]") 
                    for a_note in soup.find_all('a', class_=lambda c: c and 'note' in c.lower()):
                        a_note.replace_with(f"[{a_note.get_text(strip=True)}]")
                else:
                    for sup in soup.find_all('sup'): sup.decompose()
                    for popup in soup.find_all('div', class_=lambda c: c and 'popup' in c): popup.decompose()
                    
                verse_dict[v_num] = {'text': soup.get_text(separator='', strip=True), 'footnotes': paired_footnotes}
        return verse_dict
    except Exception as e: return {"error": f"連線錯誤: {str(e)}"}

# --- 產生 PDF ---
def generate_pdf(text_content):
    if not HAS_REPORTLAB or not FONT_LOADED: return None
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    verse_style = ParagraphStyle('VerseStyle', parent=styles['Normal'], fontName='NotoSansTC', fontSize=14, leading=22, spaceAfter=8, wordWrap='CJK', leftIndent=40, firstLineIndent=-40)
    footnote_style = ParagraphStyle('FootnoteStyle', parent=styles['Normal'], fontName='NotoSansTC', fontSize=11, leading=17, spaceAfter=6, wordWrap='CJK', leftIndent=40, firstLineIndent=-40, textColor="#555555")
    title_style = ParagraphStyle('TitleStyle', parent=styles['Normal'], fontName='NotoSansTC', fontSize=16, leading=24, spaceAfter=12, textColor="#1F4E79")
    
    story = []
    for line in text_content.split('\n'):
        line = line.strip()
        if not line: continue
        elif line == SEPARATOR_LINE: story.append(Spacer(1, 15))
        elif line == FOOTNOTE_SEPARATOR: story.append(Spacer(1, 20))
        elif line == FOOTNOTE_TITLE: story.append(Paragraph(f"<b>{line}</b>", title_style))
        elif line in FULL_BIBLE_BOOKS: story.append(Paragraph(f"<b>{line}</b>", title_style))
        elif "｜" in line: story.append(Paragraph(line, footnote_style))
        else: story.append(Paragraph(line, verse_style))
    try:
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
    except Exception: return None

# --- ★ 全新重寫：極致排版的高清圖片引擎 (PIL) ★ ---
def generate_image(text_content):
    """產出帶有凸排、層次分明、完美斷行的高解析度圖片，供長按儲存"""
    if not HAS_PIL or not os.path.exists(FONT_PATH): return None
    
    # 解析度拉高，確保圖片在 Retina 螢幕上也很清晰
    SCALE = 2
    font_size = 22 * SCALE
    line_spacing = 8 * SCALE
    margin = 50 * SCALE
    max_width = 800 * SCALE
    usable_width = max_width - 2 * margin
    
    try: 
        font = ImageFont.truetype(FONT_PATH, font_size)
        # 註解使用較小的字體
        font_small = ImageFont.truetype(FONT_PATH, int(font_size * 0.85))
        # 標題使用較大的字體
        font_title = ImageFont.truetype(FONT_PATH, int(font_size * 1.2))
    except Exception: return None 

    wrapped_lines = [] # (text, x_offset, type) type: 'verse', 'footnote', 'title', 'spacer'
    
    for line in text_content.split('\n'):
        line = line.strip()
        if not line: continue

        if line == FOOTNOTE_SEPARATOR:
            wrapped_lines.append(("_SPACER_", 0, "spacer"))
            wrapped_lines.append(("━━━━━━━━━━━━━", 0, "spacer"))
            wrapped_lines.append(("_SPACER_", 0, "spacer"))
            continue

        if line == FOOTNOTE_TITLE or line in FULL_BIBLE_BOOKS:
            wrapped_lines.append(("_SPACER_", 0, "spacer"))
            wrapped_lines.append((line, 0, "title"))
            wrapped_lines.append(("_SPACER_", 0, "spacer"))
            continue
            
        if line == SEPARATOR_LINE:
            wrapped_lines.append(("_SPACER_", 0, "spacer"))
            wrapped_lines.append(("-" * 20, 0, "spacer")) 
            wrapped_lines.append(("_SPACER_", 0, "spacer"))
            continue
            
        is_footnote = "｜" in line
        current_font = font_small if is_footnote else font

        indent_width = 0
        match = re.match(r'^([一-龥]*\s*\d+:\d+(?:\s*｜\s*\[[^\]]+\])?\s+)', line)
        if match:
            prefix = match.group(1)
            try: indent_width = current_font.getlength(prefix)
            except: indent_width = current_font.getsize(prefix)[0]

        current_line = ""
        is_first_line = True
        line_type = "footnote" if is_footnote else "verse"
        
        for char in line:
            test_line = current_line + char
            try: text_len = current_font.getlength(test_line)
            except: text_len = current_font.getsize(test_line)[0] 
            
            current_max_width = usable_width if is_first_line else (usable_width - indent_width)
            
            if text_len > current_max_width:
                wrapped_lines.append((current_line, 0 if is_first_line else indent_width, line_type))
                current_line = char
                is_first_line = False
            else:
                current_line = test_line
                
        if current_line:
            wrapped_lines.append((current_line, 0 if is_first_line else indent_width, line_type))
            
        wrapped_lines.append(("_VERSE_SPACER_", 0, "spacer")) 

    # 計算總高度
    total_height = 2 * margin
    for text, _, l_type in wrapped_lines:
        if text == "_SPACER_": total_height += int(font_size * 0.8)
        elif text == "_VERSE_SPACER_": total_height += int(font_size * 0.4)
        elif l_type == "title": total_height += int(font_size * 1.2) + line_spacing
        elif l_type == "footnote": total_height += int(font_size * 0.85) + int(line_spacing * 0.8)
        else: total_height += font_size + line_spacing
            
    img = Image.new('RGB', (max_width, total_height), color=(250, 250, 250)) # 微帶暖色的護眼白底
    draw = ImageDraw.Draw(img)
    
    y_text = margin
    for text, x_offset, l_type in wrapped_lines:
        if text == "_SPACER_":
            y_text += int(font_size * 0.8)
            continue
        if text == "_VERSE_SPACER_":
            y_text += int(font_size * 0.4)
            continue
            
        if l_type == "title":
            draw.text((margin, y_text), text, font=font_title, fill=(31, 78, 121))
            y_text += int(font_size * 1.2) + line_spacing
        elif l_type == "footnote":
            draw.text((margin + x_offset, y_text), text, font=font_small, fill=(100, 100, 100))
            y_text += int(font_size * 0.85) + int(line_spacing * 0.8)
        else:
            # 一般經文
            draw.text((margin + x_offset, y_text), text, font=font, fill=(30, 30, 30))
            y_text += font_size + line_spacing
        
    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


# --- Streamlit 介面邏輯 ---
st.set_page_config(page_title="恢復本經節抓取器", layout="centered")

# --- 注入 CSS：全面適應深淺色，並隱藏煩人的 Press Enter 浮水印 ---
st.markdown("""
    <style>
    label[data-testid="stWidgetLabel"] p { font-size: 20px !important; font-weight: bold !important; }
    div.stTextInput input { font-size: 20px !important; line-height: 1.6 !important; padding: 15px !important; height: 60px !important; }
    
    /* ★ 隱藏 "Press Enter to apply" 的礙眼浮水印 ★ */
    div[data-testid="InputInstructions"] { display: none !important; }
    
    div.stRadio div[data-testid="stMarkdownContainer"] p, div.stRadio div[data-testid="stMarkdownContainer"] span { font-size: 20px !important; line-height: 1.6 !important; }
    div.stCheckbox div[data-testid="stMarkdownContainer"] p, div.stCheckbox div[data-testid="stMarkdownContainer"] span { font-size: 20px !important; line-height: 1.6 !important; }
    div.stCheckbox { padding-top: 10px !important; padding-bottom: 10px !important; }
    div.stButton > button { font-size: 20px !important; font-weight: bold !important; padding: 12px 20px !important; height: auto !important; }
    
    /* 置中顯示長按下載提示 */
    .img-instruction { text-align:center; color:#B22222; font-weight:bold; margin-top:20px; font-size:18px;}
    </style>
    """, unsafe_allow_html=True)

if not os.path.exists(FONT_PATH):
    st.error("⚠️ 系統找不到 `NotoSansTC-VariableFont_wght.ttf`！請確認您的 GitHub 專案根目錄下有這個檔案。")

st.title("📖 恢復本經節抓取工具")

if "query" not in st.session_state:
    st.session_state.query = ""
if "final_text" not in st.session_state:
    st.session_state.final_text = ""
if "do_search" not in st.session_state:
    st.session_state.do_search = False
if "show_img" not in st.session_state:
    st.session_state.show_img = False

def trigger_search():
    st.session_state.do_search = True
    st.session_state.show_img = False # 重新搜尋時隱藏圖片

def clear_text():
    st.session_state.query = ""
    st.session_state.final_text = ""
    st.session_state.do_search = False
    st.session_state.show_img = False

output_mode = st.radio(
    "請選擇輸出排版模式：",
    options=["模式 1：每節顯示書名簡寫 (例如：可 1:1)", "模式 2：頂部顯示完整書名 (例如：馬可福音)"],
    index=1, horizontal=False 
)

include_footnotes = st.checkbox("📖 包含註解 (經文標示出處，並將完整註解整理於最下方)", value=False)

st.markdown("### 🎙️ 請用語音或鍵盤輸入經節")
st.markdown("*提示：唸完後直接按下鍵盤的 **「Enter / 搜尋」** 即可自動查詢。*")

user_input = st.text_input(
    "", 
    key="query", 
    on_change=trigger_search,
    placeholder="例如：馬可福音一章一到五節"
)

col1, col2 = st.columns([1, 4])
with col1: btn_start = st.button("🚀 開始抓取", type="primary")
with col2: st.button("🗑️ 清除內容", on_click=clear_text)

if btn_start or st.session_state.do_search:
    st.session_state.do_search = False 
    st.session_state.show_img = False
    
    if not user_input.strip():
        st.warning("請輸入內容！")
    else:
        st.info("正在透過 API 抓取中，請稍候...")
        progress_bar = st.progress(0)
        tasks = parse_input_string(user_input)
        
        final_lines = []
        all_footnotes_list = [] 
        current_book_no = None
        total_tasks = len(tasks)
        
        for i, t in enumerate(tasks):
            progress_bar.progress((i + 1) / total_tasks)
            if t['ch_start'] > t['ch_end']: t['ch_end'] = t['ch_start']
            
            for current_ch in range(t['ch_start'], t['ch_end'] + 1):
                verse_dict = fetch_verse_dict(t['no'], current_ch, include_footnotes)
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
                                if output_mode.startswith("模式 2"):
                                    final_lines.append(BOOK_FULL_MAP.get(t['name'], t['name']))
                                current_book_no = t['no']
                            
                            content = verse_dict[v]['text']
                            prefix = f"{t['name']} {current_ch}:{v}" if output_mode.startswith("模式 1") else f"{current_ch}:{v}"
                            final_lines.append(f"{prefix} {content}")
                                
                            if include_footnotes and verse_dict[v]['footnotes']:
                                for fn_text in verse_dict[v]['footnotes']:
                                    all_footnotes_list.append(f"{prefix} ｜ {fn_text}")
                            
                    if not found_any:
                        final_lines.append(f"[{t['name']} {current_ch}:{start_v} 無此節]")
                time.sleep(0.1) 

        if include_footnotes and all_footnotes_list:
            final_lines.append(FOOTNOTE_SEPARATOR)
            final_lines.append(FOOTNOTE_TITLE)
            final_lines.extend(all_footnotes_list)

        if not final_lines:
            st.error("找不到任何經文，請檢查您的輸入是否正確。")
        else:
            st.session_state.final_text = "\n".join(final_lines)

if st.session_state.final_text:
    final_text = st.session_state.final_text
    st.success("🎉 抓取完成！")
    
    with st.container(height=400):
        st.code(final_text, language="text")
    
    st.write("### 📥 分享與匯出")
    
    # 匯出按鈕區
    dl_col1, dl_col2, dl_col3 = st.columns(3)
    
    with dl_col1:
        st.download_button("📝 純文字 (.txt)", data=final_text, file_name="bible_verses.txt", mime="text/plain", use_container_width=True)
        
    with dl_col2:
        # 按下後，改變狀態來顯示下方的圖片
        if st.button("🖼️ 產生長圖 (推薦)", type="primary", use_container_width=True):
            st.session_state.show_img = True
            
    with dl_col3:
        if HAS_REPORTLAB and FONT_LOADED:
            pdf_data = generate_pdf(final_text)
            if pdf_data:
                b64_pdf = base64.b64encode(pdf_data).decode('utf-8')
                href = f'<a href="data:application/pdf;base64,{b64_pdf}" download="bible_verses.pdf" target="_blank" style="display:block; width:100%; text-align:center; padding:10px 0; border-radius:0.5rem; font-size:18px; font-weight:bold; color:rgb(49, 51, 63); background-color:white; border:1px solid rgba(49,51,63,0.2); text-decoration:none;">📄 PDF版</a>'
                st.markdown(href, unsafe_allow_html=True)
            else:
                st.button("📄 PDF (錯誤)", disabled=True, use_container_width=True)
        else:
            st.button("📄 缺字型", disabled=True, use_container_width=True)

    # ★ 終極殺招：直接在網頁上顯示高清圖片，供長按下載
    if st.session_state.show_img:
        st.markdown('<div class="img-instruction">👇 請「長按」下方圖片，選擇「分享至 LINE」或「儲存影像」👇</div>', unsafe_allow_html=True)
        img_data = generate_image(final_text)
        if img_data:
            st.image(img_data, use_container_width=True)
        else:
            st.error("圖片產生失敗，請確認字型檔案是否正確。")
