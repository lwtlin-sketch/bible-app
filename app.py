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

def parse_input_string(input_str):
    input_str = normalize_string(input_str)
    raw_items = re.split(r'[,，、\n]+', input_str)
    parsed_items = []
    
    last_book_no = None
    last_book_name = ""
    last_chapter_val = None # 新增：記錄上一次的章數
    
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
        
        # 如果書卷改變了，或者明確指定了新書卷，章數記憶要重置
        if curr_book_no is not None:
            last_book_no = curr_book_no
            last_book_name = curr_book_name
            last_chapter_val = None # 換書了，重置章數
        elif last_book_no is not None:
            # 沿用上一卷書
            curr_book_no = last_book_no
            curr_book_name = last_book_name
        else:
            continue # 無法辨識書卷，跳過

        # 2. 處理後綴 (上/下)
        suffix = ""
        match_suffix = re.search(r'([上下ab])$', remain, re.IGNORECASE)
        if match_suffix:
            suffix = match_suffix.group(1)
            remain = remain[:-1].strip()

        # 3. 處理區間
        range_parts = re.split(r'[~～-]', remain)
        main_part = range_parts[0].strip()
        end_part = range_parts[1].strip() if len(range_parts) > 1 else None
        
        # 4. 解析章節 (核心邏輯修正)
        chapter = 1
        v_start = 1
        v_end = 1
        
        # 格式 A: 中文+數字 (如: 五20, 七9) -> 章+節
        match_mixed = re.match(r'^([一二三四五六七八九十]+)(\d+)$', main_part)
        
        # 格式 B: 分隔符 (如: 5:20)
        match_split = re.split(r'[:\s]+', main_part)
        
        if match_mixed:
            # "七9" -> 第7章 第9節
            chapter = cn_to_int(match_mixed.group(1))
            v_start = int(match_mixed.group(2))
            last_chapter_val = chapter # 更新章數記憶
            
        elif len(match_split) >= 2:
            # "5:20"
            chapter = cn_to_int(match_split[0])
            v_start = cn_to_int(match_split[1])
            last_chapter_val = chapter # 更新章數記憶
            
        elif len(match_split) == 1:
            val_str = match_split[0]
            val = cn_to_int(val_str)
            
            # === 關鍵判斷邏輯 ===
            # 如果是純阿拉伯數字 (如 "5")
            if val_str.isdigit():
                if last_chapter_val is not None:
                    # 如果前面已經有章數 (如: 啟一1, 5)，視為 "節"
                    chapter = last_chapter_val
                    v_start = val
                else:
                    # 如果前面沒章數 (如: 啟5)，視為 "章"
                    chapter = val
                    v_start = 1
                    last_chapter_val = chapter
            else:
                # 如果是中文數字 (如 "五")，視為 "章"
                chapter = val
                v_start = 1
                last_chapter_val = chapter
        
        v_end = v_start
        if end_part:
            if end_part.isdigit():
                v_end = int(end_part)
            else:
                v_end = cn_to_int(end_part)
                if v_end == 0: v_end = v_start

        parsed_items.append({
            'name': curr_book_name,
            'no': curr_book_no,
            'ch': chapter,
            'v_start': v_start,
            'v_end': v_end,
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
       - *自動修正*：支援異體字（如「啓」會自動轉為「啟」）。
    2. **分隔符號**：請使用 **逗號 (，)** 或 **換行** 來區隔不同處經節。
    3. **格式範例**：
       - **一般**：`太五20` 或 `太5:20`
       - **同一章多節**：`啟一1-2，5，9` (5和9會自動視為第1章的經節)
       - **跨章**：`太五20，六10` (自動跳轉至第6章)
       - **分段**：`提後四8 上`
       - **省略書卷**：`腓三9，五21` (第二組自動沿用腓立比書)
    
    ### 🚀 功能特色
    - **一鍵複製**：抓取後，右上角會出現複製按鈕。
    - **自動過濾**：去除網頁中的註解數字。
    - **下載存檔**：可將結果下載為 `.txt` 檔案。
    """)

st.write("輸入簡寫經節（如：太五20），自動抓取並整理格式。")

# 輸入區 - 修改預設值為您的新需求
default_text = "啟一1～2，5，9～12，七9～17，十九10"
user_input = st.text_area("請輸入經節 (可多行或逗號分隔)", value=default_text, height=100)

if st.button("開始抓取"):
    if not user_input.strip():
        st.warning("請輸入內容！")
    else:
        st.info("正在連線抓取中，請稍候...")
        
        progress_bar = st.progress(0)
        
        tasks = parse_input_string(user_input)
        final_output_blocks = []
        
        total_tasks = len(tasks)
        
        for i, t in enumerate(tasks):
            progress = (i + 1) / total_tasks
            progress_bar.progress(progress)
            
            verse_dict = fetch_verse_dict(t['no'], t['ch'])
            block_lines = []
            
            if verse_dict is None or not verse_dict:
                 block_lines.append(f"{t['name']} {t['ch']}:{t['v_start']} (無法抓取內容或無此節)")
            else:
                for v in range(t['v_start'], t['v_end'] + 1):
                    content = verse_dict.get(v, "(無內容)")
                    line = f"{t['name']} {t['ch']}:{v} {content}"
                    block_lines.append(line)
            
            final_output_blocks.append("\n".join(block_lines))
            time.sleep(0.3)

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
