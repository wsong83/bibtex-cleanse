"""conference_name.py - Standardise conference/journal names in a BibTeX file.
CSV format (3 columns): Abbreviation, Match Name, Full Name

Matching strategy (in priority order):
1. Abbreviation from series/collection -> CSV abbreviation lookup
2. Abbreviation extracted from field value -> CSV abbreviation lookup
3. Fuzzy match (rapidfuzz):
   - Journal: Clean LaTeX + Lowercase ONLY
   - Conference: Deep-simplification pipeline

Output convention:
For conference-type fields (booktitle, conference), when a replacement is made, 
the abbreviation is appended: "Full Name (ABBR)".
Journal-type fields (journal, journaltitle) keep the full name only.
"""

from __future__ import annotations
import csv
import re
import sys
from pathlib import Path
from rapidfuzz import fuzz

# ===================================================================
# Constants
# ===================================================================

TARGET_FIELDS = frozenset({'journal', 'journaltitle', 'booktitle', 'conference'})
JOURNAL_FIELDS = frozenset({'journal', 'journaltitle'})
CONFERENCE_FIELDS = frozenset({'booktitle', 'conference'})

# 月份全拼到三字母小写的映射表
_MONTH_STD = {
    'january': 'jan', 'jan': 'jan', '1': 'jan',
    'february': 'feb', 'feb': 'feb', '2': 'feb',
    'march': 'mar', 'mar': 'mar', '3': 'mar',
    'april': 'apr', 'apr': 'apr', '4': 'apr',
    'may': 'may', '5': 'may',
    'june': 'jun', 'jun': 'jun', '6': 'jun',
    'july': 'jul', 'jul': 'jul', '7': 'jul',
    'august': 'aug', 'aug': 'aug', '8': 'aug',
    'september': 'sep', 'sept': 'sep', 'sep': 'sep', '9': 'sep',
    'october': 'oct', 'oct': 'oct', '10': 'oct',
    'november': 'nov', 'nov': 'nov', '11': 'nov',
    'december': 'dec', 'dec': 'dec', '12': 'dec',
}

# ===================================================================
# LaTeX cleaning
# ===================================================================

def strip_latex(raw: str) -> str:
    """Remove LaTeX markup, preserving word structure."""
    text = re.sub(
        r"""\\text(?:trademark|registered|copyright|degree"""
        r"""|superscript|subscript|dagger|ddagger)\b\s*""",
        '', raw, flags=re.IGNORECASE,
    )
    for src, dst in [
        ('\\&', '&'), ('\\%', '%'), ('\\#', '#'), ('\\_', '_'),
        ('\\$', '$'), ('~', ' '), ('\\-', '-'), ('\\/', '/'), ('\\ ', ' '),
    ]:
        text = text.replace(src, dst)
    text = text.replace('---', ' \u2014 ').replace('--', ' \u2013 ')
    text = re.sub(r'[{}]', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def clean_latex(text: str) -> str:
    """Strip LaTeX markup for plain-text comparison."""
    return strip_latex(text)

# ===================================================================
# External Data Loading
# ===================================================================

def load_expansions(short_path: str):
    expansions = []
    with Path(short_path).open(encoding='utf-8', newline='') as fh:
        reader = csv.reader(fh)
        next(reader, None)
        for row in reader:
            if len(row) >= 2:
                short, full = row[0].strip(), row[1].strip()
                if short and full:
                    escaped = re.escape(short)
                    pattern = re.compile(rf'(?<!\w){escaped}(?!\w)')
                    expansions.append((pattern, full))
    return expansions

def load_locations(city_path: str) -> set[str]:
    locations = set()
    with Path(city_path).open(encoding='utf-8', newline='') as fh:
        reader = csv.reader(fh)
        next(reader, None)
        for row in reader:
            if len(row) >= 2:
                name = row[1].strip()
                if name:
                    locations.add(name)
    return locations

def load_conferences(csv_path: str):
    p = Path(csv_path)
    if not p.is_file():
        raise FileNotFoundError(f'Conference list not found: {csv_path}')
    
    abbr_to_full: dict[str, str] = {}
    match_entries_all: list[tuple[str, str]] = []
    match_entries_conference: list[tuple[str, str]] = []
    full_to_abbr: dict[str, str] = {}
    
    with p.open(encoding='utf-8', newline='') as fh:
        reader = csv.reader(fh)
        next(reader, None)
        for row in reader:
            if len(row) != 3:
                raise ValueError(f'Invalid row format (expected 3 columns): {row}')
            
            abbr, match_name, full_name = (col.strip() for col in row)
            
            if not match_name or not full_name:
                raise ValueError(f'Missing match_name or full_name in row: {row}')
                
            match_entries_all.append((match_name, full_name))
            
            if abbr:
                match_entries_conference.append((match_name, full_name))
                abbr_to_full[abbr.lower()] = full_name
                if full_name not in full_to_abbr:
                    full_to_abbr[full_name] = abbr
                    
    if not match_entries_all:
        raise ValueError(f'No valid entries found in {csv_path}')
        
    return abbr_to_full, match_entries_all, match_entries_conference, full_to_abbr

# ===================================================================
# Booktitle simplification (ONLY for Conferences)
# ===================================================================

_MONTHS_RE = (
    r'(?:jan(?:uary)?\.?|feb(?:ruary)?\.?|mar(?:ch)?\.?|apr(?:il)?\.?|may\.?|'
    r'jun(?:e)?\.?|jul(?:y)?\.?|aug(?:ust)?\.?|sep(?:t(?:ember)?)?\.?|'
    r'oct(?:ober)?\.?|nov(?:ember)?\.?|dec(?:ember)?\.?)'
)

# 复合日期匹配正则，不限位置，全文本捕获 (已移除 re.IGNORECASE)
_DATE_BLOCK_RE = re.compile(
    rf"""
    (?:
        # 0. 月份 + 日期区间 + 年份 (如 September 14-16, 2006)
        {_MONTHS_RE}\s+\d{{1,2}}\s*[-–]\s*\d{{1,2}}\s*[,.\s]+\s*(?:19|20)\d{{2}}
        |
        # 1. 带区间的日期 (如 May 19-23, 2019 | 19-23 June 2005)
        \d{{1,2}}\s*[-–]\s*\d{{1,2}}\s*[,.\s]+\s*{_MONTHS_RE}(?:\s*[,.\s]+\s*(?:19|20)\d{{2}})?
        |
        # 2. 完整的 日, 月, 年 (如 04, jun, 2005 | 04 June 2005)
        \d{{1,2}}\s*[,.\s]+\s*{_MONTHS_RE}(?:\s*[,.\s]+\s*(?:19|20)\d{{2}})?
        |
        # 3. 月份 + 年份 (如 May 2005 | may 2005 | 2005 May)
        (?:{_MONTHS_RE}\s*[,.\s]+\s*(?:19|20)\d{{2}}|(?:19|20)\d{{2}}\s*[,.\s]+\s*{_MONTHS_RE})
        |
        # 4. 纯数字日期格式 (如 2005-05-01, 05-2005)
        (?:(?:19|20)\d{{2}}[-/]\d{{1,2}}(?:[-/]\d{{1,2}})?|\d{{1,2}}[-/](?:19|20)\d{{2}})
        |
        # 5. 纯数字日期区间 (如 19-23)
        \b\d{{1,2}}\s*[-–]\s*\d{{1,2}}\b
        |
        # 6. 独立的纯月份单词，防误杀
        (?<![a-z]){_MONTHS_RE}(?![a-z\-])
    )
    """,
    re.VERBOSE
)

def _apply_expansions(text: str, expansions):
    for pattern, replacement in expansions:
        text = pattern.sub(replacement, text)
    return text

def _remove_trailing_noise(text: str, locations_set: set[str]) -> str:
    """Remove trailing noise using precise token-by-token stripping."""
    parts = text.split(',')
    while parts:
        last = parts[-1].strip()
        # 循环去除尾部标点符号
        while last and last[-1] in '.;:,':
            last = last[:-1]
        if not last:
            parts.pop()
            continue

        # 1. 纯年份 (如 2019)
        if re.fullmatch(r'(?:19|20)\d{2}', last):
            parts.pop()
            continue

        # 2. 单词 + 年份粘合 (如 Nano-Net 2006, SP 2019)
        m = re.fullmatch(r'(.+?)\s+(?:19|20)\d{2}$', last)
        if m:
            remaining = m.group(1).strip()
            if not remaining:
                parts.pop()
            elif remaining in locations_set:
                parts.pop()
            else:
                parts[-1] = remaining
                break
            continue

        # 3. 纯数字日期区间 (如 19-23)
        if re.fullmatch(r'\d{1,2}\s*[-–]\s*\d{1,2}', last):
            parts.pop()
            continue

        # 4. 月份或月份开头 (如 may, may 19) - 已移除 re.I
        if re.match(_MONTHS_RE, last):
            parts.pop()
            continue
        if re.match(rf'^{_MONTHS_RE}\s+\d+', last):
            parts.pop()
            continue

        # 5. 城市/国家/州 (基于字典)
        if last in locations_set:
            parts.pop()
            continue

        # 遇到正常的非噪音词汇，停止清理
        break
        
    return ','.join(parts).strip().rstrip('.')

# 提取年份和月份的辅助函数
def _extract_year(text: str) -> str | None:
    m = re.search(r'\b((?:19|20)\d{2})\b', text)
    return m.group(1) if m else None

def _extract_month(text: str) -> str | None:
    m = re.search(
        r'\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b',
        text, re.IGNORECASE
    )
    if m:
        raw_m = m.group(1).strip('.').lower()
        return _MONTH_STD.get(raw_m)
    return None

def simplify_booktitle(raw: str, expansions: list, abbr_to_full: dict, locations_set: set[str]) -> tuple[str, str | None, str | None]:
    """Simplify a CONFERENCE name for fuzzy matching.
    返回: (simplified_text, extracted_year, extracted_month)
    """
    # 1. Latex剥离
    text = strip_latex(raw)
    
    # 2. [新增] 在去除括号等清理操作之前，提前提取年份和月份
    extracted_year = _extract_year(text)
    extracted_month = _extract_month(text)
    
    # 3. 去除所有括号和其内部的字符
    text = re.sub(r'\([^)]*\)', ' ', text)
    text = re.sub(r'\[[^\]]*\]', ' ', text)
    
    # 4. 提前统一变成小写
    text = text.lower()
    
    # 5. 按照conferences.csv中的会议缩写，仅去除带有年份后缀的缩写，保留仅有缩写的情况
    for abbr in abbr_to_full.keys():
        abbr_pattern = re.compile(
            rf"(?<![a-z0-9]){re.escape(abbr)}(?:['\u2019\-\s](?:19|20)?\d{{2}})(?![a-z0-9])"
        )
        text = abbr_pattern.sub(' ', text)
    
    # 6. 利用short.csv补全缩写 (提前执行，防止后续去噪步骤吃掉缩写尾部的标点)
    text = _apply_expansions(text, expansions)
    
    # 7. 去除各式各样的日期组合及纯月份 (不限位置，全文本捕获)
    text = _DATE_BLOCK_RE.sub(' ', text)
    
    # 8. 去除表示第几次的序数词修饰 (如 1st, 2nd, 24th)
    text = re.sub(r'\b\d+(?:st|nd|rd|th)\b', ' ', text)
    
    # 9. 去除首部的纯年份 (如 2019 ieee...)
    text = re.sub(r'^\s*(?:19|20)\d{2}[\s:,\-]*', '', text)
    
    # 10. 去掉尾部的噪音 (基于精准的逐段剥离机制)
    text = _remove_trailing_noise(text, locations_set)
    
    # 11. 去掉首部或逗号后的proceedings (on/of/the完全可选，即使无附加单词也整体去掉)
    # 注意：结尾使用 \s* 而不是 \s+，确保 "proceedings" 单独存在时也能被完全删除
    text = re.sub(r'(?:(?:^|,)\s*)proceedings(?:\s+(?:of|the|on))*\s*', '', text)
    
    # 12. remove : & , / -
    text = re.sub(r'[:&,/-]+', ' ', text)
    
    # 最终清理多余空格
    return re.sub(r'\s+', ' ', text).strip(), extracted_year, extracted_month

# ===================================================================
# Abbreviation extraction
# ===================================================================

def extract_series_abbr(text: str):
    cleaned = clean_latex(text).strip()
    if not cleaned:
        return None
    cleaned = re.sub(r"[,;\s]*[''\u2019\u2018]\s*(?:19|20)?\d{2}\b", '', cleaned)
    cleaned = re.sub(r'[,;\s]+(?:19|20)\d{2}\b', '', cleaned)
    cleaned = re.sub(r'[,;\s]+$', '', cleaned).strip()
    return cleaned if cleaned else None

def extract_name_abbrs(text: str):
    """提取会议名称中所有可能的候选缩写。"""
    cleaned = clean_latex(text)
    if not cleaned:
        return

    # 规则 1: 括号内提取
    for m in re.finditer(r"\(([A-Za-z][A-Za-z0-9+-]*(?:\s+[A-Za-z0-9+-]+)*)\)", cleaned):
        abbr = m.group(1).strip()
        abbr = re.sub(r'\s+(?:19|20)\d{2}$', '', abbr)
        if abbr:
            yield abbr

    # 规则 2: 大写开头词 + 年份（不再一碰到就 return，而是遍历所有匹配）
    for m in re.finditer(r"([A-Z][A-Za-z0-9+-]{1,14})\s*[''\u2019]?\s*(?:19|20)?\d{2}\b", cleaned):
        yield m.group(1).strip()

    # 规则 3: 逗号后的词
    for m in re.finditer(r',\s*([A-Z][A-Za-z0-9+-]{1,14})\s*[.,]?\s*$', cleaned):
        yield m.group(1)

# ===================================================================
# Fuzzy matching
# ===================================================================

def fuzzy_match_best(cleaned_value: str, entries: list[tuple[str, str]]):
    if not cleaned_value:
        return None, 0.0
    best_full, best_score = None, 0.0
    for match_name, full_name in entries:
        score = (
            0.2 * fuzz.token_set_ratio(cleaned_value, match_name) +
            0.3 * fuzz.partial_ratio(cleaned_value, match_name) +
            0.5 * fuzz.token_sort_ratio(cleaned_value, match_name)
        )
        if score > best_score:
            best_score = score
            best_full = full_name
    return best_full, best_score

# ===================================================================
# Three-tier matching
# ===================================================================

def find_match(
    field_value, field_name, series_abbr, abbr_to_full, match_entries_all,
    match_entries_conference, threshold, expansions, locations_set
):
    # 只从会议名称中提取缩写，期刊名称跳过此步骤
    if field_name in CONFERENCE_FIELDS:
        # 1. 确定提取的 series 会议缩写 (互斥操作)
        extracted_abbr = None
        if series_abbr is not None:
            extracted_abbr = series_abbr.strip()
        else:
            # 如果没有 series 字段，从 field_value 中提取第一个候选
            extracted_abbr = next(extract_name_abbrs(field_value), None)
            if extracted_abbr:
                extracted_abbr = extracted_abbr.strip()
        
        # 查找该提取缩写对应的全名
        series_full = abbr_to_full.get(extracted_abbr.lower()) if extracted_abbr else None
        
        # 2. 无论如何，都执行 simplify_booktitle 和 fuzzy_match_best
        entries = match_entries_conference
        compared_as, extracted_year, extracted_month = simplify_booktitle(field_value, expansions, abbr_to_full, locations_set)
        best_full, best_score = fuzzy_match_best(compared_as, entries)
        
        # 3. 二选一逻辑及冲突判定
        if series_full is not None:
            # 存在提取到的 series 全名
            if best_full is None or best_score < threshold:
                # fuzzy 失败或得分不足，使用 series 抽取结果
                return series_full, 100.0, 'series', compared_as, extracted_abbr, extracted_year, extracted_month
            else:
                # fuzzy 得分达到阈值
                if best_full == series_full:
                    # 结果一致，没有问题，使用 series 结果记录
                    return series_full, 100.0, 'series', compared_as, extracted_abbr, extracted_year, extracted_month
                else:
                    # 结果不一致，使用 fuzzy 结果，并报告该不一致
                    return best_full, best_score, 'fuzzy-conflict', compared_as, extracted_abbr, extracted_year, extracted_month
        else:
            # 没有提取到有效的 series 全名，完全依赖 fuzzy 结果
            if best_full and best_score >= threshold:
                return best_full, best_score, 'fuzzy', compared_as, None, extracted_year, extracted_month
            else:
                return None, best_score, 'below-threshold', compared_as, None, extracted_year, extracted_month
    else:
        # 期刊逻辑保持不变
        entries = match_entries_all
        compared_as = clean_latex(field_value).lower()
        compared_as = _apply_expansions(compared_as, expansions)
        
        # 将 &, -, / 替换为空格，解体粘合的单词以提升匹配率
        compared_as = re.sub(r'[:&,/-]', ' ', compared_as)
        compared_as = re.sub(r'\s+', ' ', compared_as).strip()

        best_full, best_score = fuzzy_match_best(compared_as, entries)
        if best_full and best_score >= threshold:
            return best_full, best_score, 'fuzzy', compared_as, None, None, None

        return None, best_score, 'below-threshold', compared_as, None, None, None

# ===================================================================
# BibTeX parser / transformer
# ===================================================================
def process_bib(
    filepath: str,
    abbr_to_full, match_entries_all, match_entries_conference,
    threshold, expansions, full_to_abbr, locations_set, debug: bool = False
):
    """解析 BibTeX 文件，标准化目标字段，返回修改后的条目字典列表。"""
    # 延迟导入，避免循环依赖，并使用统一的解析模块
    from .bibtex_parse import parse_bibtex
    
    entries = parse_bibtex(filepath)
    results = []
    below_entries: dict[str, list] = {}

    for entry in entries:
        entry_key = entry.get('key', 'UNKNOWN')
        
        # 0. 读入时立即规范化月份字段为三字母小写
        if 'month' in entry:
            raw_month = entry['month'].strip().lower()
            # 查表转换，如果不在表中（比如某些错误格式），保持原样
            std_month = _MONTH_STD.get(raw_month, None)
            entry['month'] = std_month if std_month else raw_month
            if not std_month:
                print(f"[debug] {entry_key}: month '{raw_month}' kept (unknown format)", file=sys.stderr)

        # 1. 从字典中直接提取 series/collection，远比正则扒取简单可靠
        series_raw = entry.get('series') or entry.get('collection')
        series_abbr = extract_series_abbr(series_raw) if series_raw else None

        # 2. 遍历当前条目的所有字段
        for field_name in list(entry.keys()):
            if field_name not in TARGET_FIELDS:
                continue
                
            raw_value = entry[field_name]
            
            # 调用原有匹配逻辑
            repl, score, method, compared_as, extracted_abbr, extracted_year, extracted_month = find_match(
                raw_value, field_name, series_abbr, abbr_to_full, match_entries_all,
                match_entries_conference, threshold, expansions, locations_set
            )
            
            results.append({
                'key': entry_key,
                'field': field_name,
                'raw': clean_latex(raw_value),
                'matched': repl,
                'score': round(score, 1),
                'method': method
            })

            # 处理冲突警告
            if method == 'fuzzy-conflict':
                fuzzy_abbr = full_to_abbr.get(repl, "N/A")
                print(
                    f"\n[bibclean] WARNING: Series/Fuzzy mismatch for {entry_key}:\n"
                    f" Original Name : {clean_latex(raw_value)}\n"
                    f" Simplified : {compared_as}\n"
                    f" Fuzzy Match : {fuzzy_abbr}\n"
                    f" Series Extract: {extracted_abbr}", file=sys.stderr
                )

            # 年份与月份的验证和补全逻辑
            if field_name in CONFERENCE_FIELDS:
                # --- 验证与补全 Year ---
                orig_year = entry.get('year', '').strip()
                if extracted_year:
                    if not orig_year:
                        entry['year'] = extracted_year  # 补全
                    elif orig_year != extracted_year:
                        if debug:
                            print(f"[debug] {entry_key}: year mismatch. Original: {orig_year}. Booktitle: {clean_latex(raw_value)}", file=sys.stderr)
                
                # --- 验证与补全 Month ---
                orig_month = entry.get('month', '').strip()
                if extracted_month:
                    if not orig_month:
                        entry['month'] = extracted_month  # 补全
                    elif orig_month != extracted_month:
                        if debug:
                            print(f"[debug] {entry_key}: month mismatch. Original: {orig_month}. Booktitle: {clean_latex(raw_value)}", file=sys.stderr)

            # 3. 命中则直接修改字典中的值 (注意这里的缩进，必须在 for 循环内部)
            if repl is not None:
                if field_name in CONFERENCE_FIELDS and repl in full_to_abbr:
                    abbr = full_to_abbr[repl]
                    entry[field_name] = f"{repl} ({abbr})"
                else:
                    entry[field_name] = repl
            else:
                below_entries.setdefault(entry_key, []).append(
                    (field_name, clean_latex(raw_value), round(score, 1), compared_as)
                )

    if below_entries:
        print('\n[bibclean] Entries with unmatched target fields:', file=sys.stderr)
        for key in sorted(below_entries):
            unmatched_fields = below_entries[key]  # <-- 改这里
            # 计算最大长度，确保 = 号对齐（考虑 "compared-as" 的长度）
            max_len = max(len(fname) for fname, _, _, _ in unmatched_fields)
            max_len = max(max_len, len("compared-as"))
            for fname, raw, score, compared_as in unmatched_fields:
                print(f" {key}: {score}", file=sys.stderr)
                print(f" {fname:<{max_len}} = {raw}", file=sys.stderr)
                print(f" {'compared-as':<{max_len}} = {compared_as}", file=sys.stderr)

    # 返回修改后的字典列表，交由 write 模块处理
    return entries, results

