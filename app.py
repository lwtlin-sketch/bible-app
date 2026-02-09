import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import time

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
BOOK_MAP = {name: i+1 for i, name in enumerate(BIBLE_BOOKS)}

# --- 核心邏輯函式 ---

def normalize_string(s):
    """全形轉半形，並處理異體字"""
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
    """抓取單一章節的所有經文"""
    url = f"https://recoveryversion.twgbr.org/Style0A/026/read_List.php?f_BookNo={book_no}&f_ChapterNo={chapter}&f_VerseNo=1"
    verse_dict = {}
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=20)
        try:
            html_text = response.content.decode('cp950')
        except:
            try:
                html_text = response.content.decode('big5')
            except:
                html_text = response.content.decode('utf-8', errors='ignore')

        soup = BeautifulSoup(html_text, 'html.parser')
        for script in soup(["script", "style"]):
            script.extract()
            
        rows = soup.find_all('tr')
        for row in rows:
            tds = row.find_all('td')
            if len(tds) < 2: continue
            ref_text = tds[0].get_text(strip=True)
            if ':' in ref_text or '：' in ref_text:
                parts = re.split(r'[:：]', ref_text)
                if len(parts) > 1:
                    v_num_str = parts[-1].strip()
                    if v_num_str.isdigit():
                        v_num = int(v_num_str)
                        content_td = tds[1]
                        for tag in content_td.find_all(['sup', 'a']):
                            if tag.name == 'sup' or (tag.name == 'a' and 'notes' in tag.get('class', [])):
                                tag.decompose()
                        text_content = content_td.get_text(separator="", strip=True)
                        text_content = text_content.replace('\u3000', ' ').strip()
                        if text_content:
                            verse_dict[v_num] = text_content
    except Exception as e:
        return None
    return verse_dict

def parse_chapter_verse(text):
    """解析單一段落 (例如: '五20' 或 '5:20' 或 '20') 回傳 (chapter, verse, has_chapter)"""
    # 格式 A: 中文+數字 (如: 五20, 七9)
    match_mixed = re.match(r'^([一二三四五六七八九十]+)(\d+)$', text)
    if match_mixed:
        return cn_to_int(match_mixed.group(1)), int(match_mixed.group(2)), True
    
    # 格式 B: 分隔符 (如: 5:20)
    match_split = re.split(r'[:\s]+', text)
    if len(match_split) >= 2:
        return cn_to_int(match_split[0]), cn_to_int(match_split[1]), True
        
    # 格式 C: 單一數字 (如: '20' 或 '五')
    val_str = match_split[0]
    val = cn_to_int(val_str)
    
    if val_str.isdigit():
        return None, val, False # 純數字，可能是節，也可能是章，由 Context 決定
    else:
        return val, 1, True # 中文數字，通常視為章

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
        
        # 1. 判斷書卷
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
        else:
            continue

        # 2. 處理後綴
        suffix = ""
        match_suffix = re.search(r'([上下ab])$', remain, re.IGNORECASE)
        if match_suffix:
            suffix = match_suffix.group(1)
            remain = remain[:-1].strip()

        # 3. 處理區間 (關鍵邏輯修正：區分「同章範圍」與「跨章範圍」)
        range_parts = re.split(r'[~～-]', remain)
        main_part = range_parts[0].strip()
        end_part = range_parts[1].strip() if len(range_parts) > 1 else None
        
        # 解析起始點
        p_ch, p_v, has_ch = parse_chapter_verse(main_part)
        
        chapter_start = 1
        verse_start = 1
        
        if has_ch:
            chapter_start = p_ch
            verse_start = p_v
            last_chapter_val = chapter_start
        else:
            # 只有數字
            if last_chapter_val is not None:
                chapter_start = last_chapter_val
                verse_start = p_v
            else:
                chapter_start = p_ch if p_ch else p_v # 若前面沒章，視為章
                verse_start = 1
                last_chapter_val = chapter_start

        # 解析結束點
        chapter_end = chapter_start
        verse_end = verse_start
        
        if end_part:
            # 嘗試解析結束部分是否包含章 (例如 "二六56")
            e_ch, e_v, e_has_ch = parse_chapter_verse(end_part)
            
            if e_has_ch:
                # 結束點有明確章節 (如 "二六56" 或 "26:56")
                chapter_end = e_ch
                verse_end = e_v
                last_chapter_val = chapter_end # 更新記憶
            else:
                # 結束點只有數字
                if e_v > 0:
                    # 判斷這個數字是否大到像「章」？
                    # 恢復本網站的特性，如果數字很小 (如 5)，通常是同章的節
                    # 但如果使用者輸入 `太25~26` (意指25章到26章)，這很難判斷
                    # 基於您的需求 "二五14~二六56"，結束點通常會帶章
                    # 若只有 "14~56"，則視為同章
                    chapter_end = chapter_start
                    verse_end = e_v

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

# --- Streamlit 介面邏輯 ---
st.set_page_config(page_title="恢復本經節抓取器", layout="centered")

st.title("📖 恢復本經節抓取工具")

with st.expander("ℹ️ 使用說明與範例 (點擊展開)"):
    st.markdown("""
    ### 📝 輸入格式說明
    1. **書卷簡寫**：支援常見簡寫（如：太、林前、啟）。
    2. **分隔符號**：請使用 **逗號 (，)** 或 **換行** 來區隔不同處經節。
    3. **格式範例**：
       - **一般**：`太五20` 或 `太5:20`
       - **跨章範圍**：`太二五14~二六56` (自動抓取跨章經節)
       - **多章範圍**：`可二1~四34` (自動補完中間的第三章)
       - **同章多節**：`啟一1-2，5，9`
       - **省略書卷**：`腓三9，五21` (第二組沿用書卷)
    
    ### 🚀 功能特色
    - **跨章抓取**：支援如 `太25:14 ~ 26:56` 的跨章節抓取。
    - **一鍵複製**：結果顯示於代碼區塊，右上角可直接複製。
    """)

st.write("輸入簡寫經節，自動抓取並整理格式。")

# 輸入區 - 預設為您的測試案例
default_text = "太二五14~二六56，二六57~二八20，可一1~一45，二1~四34，四35~七30，七31~十12，十13~十二37"
user_input = st.text_area("請輸入經節 (可多行或逗號分隔)", value=default_text, height=150)

if st.button("開始抓取"):
    if not user_input.strip():
        st.warning("請輸入內容！")
    else:
        st.info("正在連線抓取中，因範圍較大請耐心等候...")
        
        progress_bar = st.progress(0)
        
        tasks = parse_input_string(user_input)
        final_output_blocks = []
        
        total_tasks = len(tasks)
        
        for i, t in enumerate(tasks):
            progress = (i + 1) / total_tasks
            progress_bar.progress(progress)
            
            # === 處理跨章邏輯 ===
            task_lines = []
            
            # 從起始章 跑到 結束章
            for current_ch in range(t['ch_start'], t['ch_end'] + 1):
                verse_dict = fetch_verse_dict(t['no'], current_ch)
                
                if verse_dict:
                    # 計算該章要抓的起始節與結束節
                    # 如果是起始章，從 v_start 開始；否則從第 1 節開始
                    start_v = t['v_start'] if current_ch == t['ch_start'] else 1
                    
                    # 如果是結束章，到 v_end 結束；否則抓到該章最大節數 (用 999 概括)
                    end_v = t['v_end'] if current_ch == t['ch_end'] else 999
                    
                    # 遍歷字典輸出
                    # 這裡需要將 key 排序，以免順序亂掉
                    for v in sorted(verse_dict.keys()):
                        if start_v <= v <= end_v:
                            content = verse_dict[v]
                            line = f"{t['name']} {current_ch}:{v} {content}"
                            task_lines.append(line)
                
                # 禮貌性延遲，避免大量請求被擋
                time.sleep(0.2)

            if not task_lines:
                 final_output_blocks.append(f"{t['name']} {t['ch_start']}:{t['v_start']} (無法抓取或無內容)")
            else:
                final_output_blocks.append("\n".join(task_lines))

        final_text = "\n\n".join(final_output_blocks)
        
        st.success("抓取完成！")
        
        st.subheader("抓取結果")
        st.caption("請點擊下方區塊右上角的 📋 圖示即可複製全部內容")
        
        st.code(final_text, language="text")
        
        st.download_button(
            label="下載為 .txt 檔案",
            data=final_text,
            file_name="bible_verses.txt",
            mime="text/plain"
        )
