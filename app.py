import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import time
import io

# 嘗試載入 PDF 套件
try:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

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
    """API 完美破解版 (v7.3)"""
    query = f"?VERSION=1&output[]=content&output[]=unit_code&output[]=segment_code&chapter_code={book_no}&section_code={chapter}&ORDER=id"
    url = f"https://www.recoveryversion.com.tw//api/getVerses{query}"
    
    verse_dict = {}
    
    try:
        headers = {
            'Accept': '*/*',
            'Accept-Language': 'zh-TW,zh;q=0.9',
            'Origin': 'https://recoveryversion.twgbr.org',
            'Referer': 'https://recoveryversion.twgbr.org/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'
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
                    
                clean_text = soup.get_text(separator='', strip=True)
                verse_dict[v_num] = clean_text
                
        return verse_dict

    except Exception as e:
        return {"error": f"連線錯誤: {str(e)}"}

def parse_chapter_verse(text):
    match_mixed = re.match(r'^([一二三四五六七八九十]+)(\d+)$', text)
    if match_mixed:
        return cn_to_int(match_mixed.group(1)), int(match_mixed.group(2)), True
    match_split = re.split(r'[:\s]+', text)
    if len(match_split) >= 2:
        return cn_to_int(match_split[0]), cn_to_int(match_split[1]), True
    val_str = match_split[0]
    val = cn_to_int(val_str)
    if val_str.isdigit():
        return None, val, False
    else:
        return val, 1, True

def parse_input_string(input_str):
    input_str = normalize_string(input_str)
    raw_items = re.split(r'[,，、\n]+', input_str)
    parsed_items = []
    last_book_no = None
    last_book_name = ""
    last_chapter_val = None 
    sorted_books = sorted(BIBLE_BOOKS, key=len, reverse=True)
    
    for item in raw_items:
        item = item.strip()
        if not item: continue
        curr_book_no = None
        curr_book_name = ""
        remain = item
        for b in sorted_books:
            if remain.startswith(b):
                curr_book_name = b
                curr_book_no = BOOK_MAP[b]
                remain = remain[len(b):].strip()
                break
        
        if curr_book_no is not None:
            last_book_no = curr_book_no
            last_book_name = curr_book_name
            last_chapter_val = None 
        elif last_book_no is not None:
            curr_book_no = last_book_no
            curr_book_name = last_book_name
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
            if last_chapter_val is not None:
                chapter_start, verse_start = last_chapter_val, p_v
            else:
                chapter_start, verse_start = (p_ch if p_ch else p_v), 1
                last_chapter_val = chapter_start

        chapter_end, verse_end = chapter_start, verse_start
        if end_part:
            e_ch, e_v, e_has_ch = parse_chapter_verse(end_part)
            if e_has_ch:
                chapter_end, verse_end = e_ch, e_v
                last_chapter_val = chapter_end
            else:
                if e_v > 0: chapter_end, verse_end = chapter_start, e_v

        parsed_items.append({
            'name': curr_book_name,
            'no': curr_book_no,
            'ch_start': chapter_start,
            'v_start': verse_start,
            'ch_end': chapter_end,
            'v_end': verse_end,
            'suffix': suffix
        })
        
    return parsed_items

# --- PDF 產生函式 ---
def generate_pdf(text_content):
    if not HAS_REPORTLAB: return None
    
    # 註冊繁體中文免安裝字型 (內建於 Adobe PDF 標準)
    pdfmetrics.registerFont(UnicodeCIDFont('MSung-Light'))
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    
    # 設定經文樣式：14號字，自動換行
    verse_style = ParagraphStyle(
        'VerseStyle', parent=styles['Normal'], fontName='MSung-Light',
        fontSize=14, leading=22, wordWrap='CJK'
    )
    # 設定書卷標題樣式：16號字加粗，置中或靠左
    title_style = ParagraphStyle(
        'TitleStyle', parent=styles['Normal'], fontName='MSung-Light',
        fontSize=16, leading=24, spaceAfter=10, textColor="#1F4E79"
    )
    
    story = []
    lines = text_content.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            story.append(Spacer(1, 10))
        elif line == "-----":
            story.append(Spacer(1, 15))
        elif line in FULL_BIBLE_BOOKS: # 若為書卷全名
            story.append(Paragraph(f"<b>{line}</b>", title_style))
        else: # 一般經文
            story.append(Paragraph(line, verse_style))
            
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# --- Streamlit 介面邏輯 ---
st.set_page_config(page_title="恢復本經節抓取器", layout="centered")
st.title("📖 恢復本經節抓取工具")

# 初始化 Session State (用來控制文字框預設與清除)
if "user_input" not in st.session_state:
    st.session_state.user_input = "可一1~5\n創一1~3" # 預設文字變少

def clear_text():
    st.session_state.user_input = ""

st.text_area("請輸入經節 (可多行或逗號分隔)", key="user_input", height=150)

# 排列兩個按鈕
col1, col2 = st.columns([1, 4])
with col1:
    btn_start = st.button("🚀 開始抓取", type="primary")
with col2:
    st.button("🗑️ 清除內容", on_click=clear_text)

if btn_start:
    input_text = st.session_state.user_input
    if not input_text.strip():
        st.warning("請輸入內容！")
    else:
        st.info("正在透過 API 高速連線抓取中，請稍候...")
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
                            # 【新增功能 2】判斷是否需要印出「書卷全名」與「分隔線」
                            if t['no'] != current_book_no:
                                if current_book_no is not None:
                                    final_lines.append("-----") # 不同書卷之間加上分隔線
                                full_book_name = BOOK_FULL_MAP.get(t['name'], t['name'])
                                final_lines.append(full_book_name) # 加上完整的書卷名稱
                                current_book_no = t['no']
                            
                            content = verse_dict[v]
                            final_lines.append(f"{t['name']} {current_ch}:{v} {content}")
                            
                    if not found_any:
                        final_lines.append(f"[{t['name']} {current_ch}:{start_v} 無此節]")
                
                time.sleep(0.1) 

        if not final_lines:
            st.error("找不到任何經文，請檢查輸入格式。")
        else:
            final_text = "\n".join(final_lines)
            st.success("🎉 抓取完成！")
            
            st.subheader("抓取結果")
            st.code(final_text, language="text")
            
            # --- 匯出按鈕區 ---
            if not HAS_REPORTLAB:
                st.warning("⚠️ 系統未安裝 `reportlab` 套件，無法提供 PDF 下載功能。(請使用 pip install reportlab 安裝)")
                
            dl_col1, dl_col2 = st.columns(2)
            with dl_col1:
                st.download_button("📝 下載為 .txt 檔案", data=final_text, file_name="bible_verses.txt", mime="text/plain")
            
            with dl_col2:
                if HAS_REPORTLAB:
                    pdf_data = generate_pdf(final_text)
                    if pdf_data:
                        st.download_button("📄 下載為 14號字 PDF", data=pdf_data, file_name="bible_verses.pdf", mime="application/pdf")
