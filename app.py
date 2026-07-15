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
    """v7.0：使用官方隱藏 API 直接獲取資料，速度最快、最穩定"""
    url = "https://www.recoveryversion.com.tw/api/getVerses"
    # 根據取得的 API 結構，chapter_code = 卷，section_code = 章
    query_string = f"?VERSION=1&output[]=content&output[]=unit_code&chapter_code={book_no}&section_code={chapter}&ORDER=id"
    verse_dict = {}
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept': 'application/json, text/plain, */*'
        }
        
        # 呼叫 API
        response = requests.get(url + query_string, headers=headers, timeout=15)
        response.raise_for_status() # 若連線失敗則拋出例外
        data = response.json()
        
        # API 通常回傳陣列 (List)，或是包在一個物件裡，我們動態處理
        items = data if isinstance(data, list) else data.get('data', [])
        
        # 如果 data 是一個字典且沒有 'data' 鍵，找出裡面是陣列的欄位
        if not items and isinstance(data, dict):
            for key in data:
                if isinstance(data[key], list):
                    items = data[key]
                    break
        
        for item in items:
            v_num = int(item.get('unit_code', 0)) # API 中的 'unit_code' 就是節數
            content_html = item.get('content', '')
            
            if v_num > 0 and content_html:
                # 雖然是 API，但內容可能還是夾帶了註解的 HTML 標籤
                # 透過 BeautifulSoup 把那些註解數字和多餘標籤剝除
                soup = BeautifulSoup(content_html, 'html.parser')
                
                # 移除所有的 <sup> (註解數字)
                for sup in soup.find_all('sup'):
                    sup.decompose()
                # 移除隱藏的彈出視窗
                for popup in soup.find_all('div', class_=lambda c: c and 'popup' in c):
                    popup.decompose()
                    
                # 取得乾淨的純文字經文
                clean_text = soup.get_text(separator='', strip=True)
                verse_dict[v_num] = clean_text
                
        return verse_dict

    except Exception as e:
        return {"error": str(e)}

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
        else:
            continue

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
                if e_v > 0:
                    chapter_end, verse_end = chapter_start, e_v

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
       - **跨章範圍**：`太二五14~二六56` 
    """)

default_text = "太二五14~二六56，二六57~二八20，可一1~一45，二1~四34，四35~七30，七31~十12，十13~十二37"
user_input = st.text_area("請輸入經節 (可多行或逗號分隔)", value=default_text, height=150)

if st.button("開始抓取"):
    if not user_input.strip():
        st.warning("請輸入內容！")
    else:
        st.info("正在透過 API 高速連線抓取中，請稍候...")
        progress_bar = st.progress(0)
        tasks = parse_input_string(user_input)
        final_output_blocks = []
        total_tasks = len(tasks)
        
        for i, t in enumerate(tasks):
            progress = (i + 1) / total_tasks
            progress_bar.progress(progress)
            task_lines = []
            
            for current_ch in range(t['ch_start'], t['ch_end'] + 1):
                verse_dict = fetch_verse_dict(t['no'], current_ch)
                
                # 若發生錯誤，印出錯誤訊息幫助除錯
                if verse_dict and "error" in verse_dict:
                    st.error(f"抓取 {t['name']} 第 {current_ch} 章時發生錯誤: {verse_dict['error']}")
                    continue
                
                if verse_dict:
                    start_v = t['v_start'] if current_ch == t['ch_start'] else 1
                    end_v = t['v_end'] if current_ch == t['ch_end'] else 999
                    
                    for v in sorted(verse_dict.keys()):
                        if start_v <= v <= end_v:
                            content = verse_dict[v]
                            line = f"{t['name']} {current_ch}:{v} {content}"
                            task_lines.append(line)
                
                time.sleep(0.1) # 因為是 API，延遲可以縮短，抓取更順暢

            if not task_lines:
                 final_output_blocks.append(f"{t['name']} {t['ch_start']}:{t['v_start']} (無法抓取或無內容)")
            else:
                final_output_blocks.append("\n".join(task_lines))

        final_text = "\n\n".join(final_output_blocks)
        st.success("🎉 抓取完成！")
        st.subheader("抓取結果")
        st.caption("請點擊下方區塊右上角的 📋 圖示即可複製全部內容")
        st.code(final_text, language="text")
        st.download_button(
            label="下載為 .txt 檔案",
            data=final_text,
            file_name="bible_verses.txt",
            mime="text/plain"
        )
