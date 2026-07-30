if btn_start:
    if not user_input.strip():
        st.warning("請輸入內容！")
    else:
        tasks = parse_input_string(user_input)
        
        # 1. 找出所有「不重複」的需要抓取的 (書卷號碼, 章節)
        unique_fetches = set()
        for t in tasks:
            if t['ch_start'] > t['ch_end']: t['ch_end'] = t['ch_start']
            for current_ch in range(t['ch_start'], t['ch_end'] + 1):
                unique_fetches.add((t['no'], current_ch))
        
        # ★ 防呆機制：限制最大查詢量
        if len(unique_fetches) > 40:
            st.error("⚠️ 一次查詢的章節數量過多（超過 40 章）。為了保護伺服器不崩潰，請分批查詢！")
            st.stop()

        st.info(f"⚡ 正在並行抓取 {len(unique_fetches)} 個章節中，請稍候...")
        progress_bar = st.progress(0)
        
        # ★ 多執行緒並行抓取 (只抓取不重複的章節，效率更高！)
        results_map = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            # 建立任務清單，把 (書卷號碼, 章節) 當作獨一無二的 Tuple Key
            future_to_req = {
                executor.submit(fetch_verse_dict, req[0], req[1], include_footnotes): req 
                for req in unique_fetches
            }
            for i, future in enumerate(concurrent.futures.as_completed(future_to_req)):
                req = future_to_req[future]  
                results_map[req] = future.result() # 完美儲存結果，不再報錯
                progress_bar.progress((i + 1) / len(unique_fetches))

        final_lines = []
        all_footnotes_list = [] 
        current_book_no = None
        
        # 2. 依照原本輸入順序重組文字
        for t in tasks:
            for current_ch in range(t['ch_start'], t['ch_end'] + 1):
                # 透過 (書卷號碼, 章節) 取回資料
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
                                for fn_text in verse_dict[v]['footnotes']:
                                    all_footnotes_list.append(f"{prefix} ｜ {fn_text}")
                            
                    if not found_any:
                        final_lines.append(f"[{t['name']} {current_ch}:{start_v} 無此節]")

        if include_footnotes and all_footnotes_list:
            final_lines.append(FOOTNOTE_SEPARATOR)
            final_lines.append(FOOTNOTE_TITLE)
            final_lines.extend(all_footnotes_list)

        if not final_lines: 
            st.error("找不到任何經文，請檢查您的輸入是否正確。")
        else: 
            st.session_state.final_text = "\n".join(final_lines)
