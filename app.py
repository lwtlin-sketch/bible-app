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

def normalize_string(s):
    """全形轉半形"""
    r = ""
    for char in s:
        code = ord(char)
        if code == 12288: code = 32
        elif 65281 <= code <= 65374: code -= 65248
        r += chr(code)
    return r.strip()

def cn_to_int(s):
    """中文轉數字"""
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
    """
    抓取整章經文，並回傳字典 {節數: 內容}
    不再回傳字串，以便後續靈活排版
    """
    # 這裡 f_VerseNo 設為 1，抓取整頁解析
    url = f"https://recoveryversion.twgbr.org/Style0A/026/read_List.php?f_BookNo={book_no}&f_ChapterNo={chapter}&f_VerseNo=1"
    
    verse_dict = {}
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=20)
        
        # 強制使用 cp950 解碼 (解決 Big5 亂碼)
        try:
            html_text = response.content.decode('cp950')
        except:
            try:
                html_text = response.content.decode('big5')
            except:
                html_text = response.content.decode('utf-8', errors='ignore')

        soup = BeautifulSoup(html_text, 'html.parser')
        
        # 移除干擾元素
        for script in soup(["script", "style"]):
            script.extract()
            
        rows = soup.find_all('tr')
        
        for row in rows:
            tds = row.find_all('td')
            if len(tds) < 2: continue
            
            # 處理經節號 (格式如 89:14)
            ref_text = tds[0].get_text(strip=True)
            if ':' in ref_text or '：' in ref_text:
                parts = re.split(r'[:：]', ref_text)
                if len(parts) > 1:
                    v_num_str = parts[-1].strip()
                    
                    if v_num_str.isdigit():
                        v_num = int(v_num_str)
                        content_td = tds[1]
                        
                        # 移除註解
                        for sup in content_td.find_all('sup'):
                            sup.decompose()
                        for note_link in content_td.find_all('a', class_='notes'):
                            note_link.decompose()
                        
                        # 取得純文字
                        text_content = content_td.get_text(separator="", strip=True)
                        text_content = text_content.replace('\u3000', ' ').strip()
                        
                        if text_content:
                            verse_dict[v_num] = text_content
                            
    except Exception as e:
        print(f"抓取錯誤: {str(e)}")
        return None

    return verse_dict

def parse_input_string(input_str):
    input_str = normalize_string(input_str)
    raw_items = re.split(r'[,，、\n]+', input_str)
    parsed_items = []
    
    last_book_no = None
    last_book_name = ""
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
                last_book_no = curr_book_no
                last_book_name = curr_book_name
                break
        
        if curr_book_no is None:
            if last_book_no:
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
        
        chapter = 1
        v_start = 1
        v_end = 1
        
        match_mixed = re.match(r'^([一二三四五六七八九十]+)(\d+)$', main_part)
        match_split = re.split(r'[:\s]+', main_part)
        
        if match_mixed:
            chapter = cn_to_int(match_mixed.group(1))
            v_start = int(match_mixed.group(2))
        elif len(match_split) >= 2:
            chapter = cn_to_int(match_split[0])
            v_start = cn_to_int(match_split[1])
        elif len(match_split) == 1:
            val = cn_to_int(match_split[0])
            chapter = val
            v_start = 1
            
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

if __name__ == "__main__":
    default_input = "太五20，詩八九14，腓三9，林後三8 ～ 9，五21，提後四8 上"
    print(f"預設範例：{default_input}")
    user_input = input("請輸入經節 (按 Enter 直接使用範例): ")
    
    if not user_input.strip():
        user_input = default_input
        
    print("\n正在抓取...\n")
    tasks = parse_input_string(user_input)
    
    final_output_blocks = [] # 儲存每個查詢區塊的文字
    
    for t in tasks:
        print(f"處理: {t['name']} {t['ch']}:{t['v_start']}...")
        
        verse_dict = fetch_verse_dict(t['no'], t['ch'])
        
        # 準備這個區塊的輸出內容
        block_lines = []
        
        if verse_dict is None or not verse_dict:
             block_lines.append(f"{t['name']} {t['ch']}:{t['v_start']} (無法抓取內容或無此節)")
        else:
            # 針對區間 loop (例如 8-9 節)
            for v in range(t['v_start'], t['v_end'] + 1):
                content = verse_dict.get(v, "(無內容)")
                # 格式化輸出： 書名 章:節 經文
                line = f"{t['name']} {t['ch']}:{v} {content}"
                block_lines.append(line)
        
        # 將這個區塊的行合併
        final_output_blocks.append("\n".join(block_lines))
        
        # 禮貌性延遲
        time.sleep(0.5)

    # 用兩個換行符號連接各個區塊，達到空一行的效果
    final_text = "\n\n".join(final_output_blocks)
    
    print("\n" + "="*30 + "\n")
    print(final_text)
    
    with open("bible_result.txt", "w", encoding="utf-8-sig") as f:
        f.write(final_text)
    print("\n已存檔至 bible_result.txt")