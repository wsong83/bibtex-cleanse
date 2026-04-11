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
import argparse
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
    if not p.is_file(): raise FileNotFoundError(f'Conference list not found: {csv_path}')
    
    abbr_to_full: dict[str, str] = {}
    match_entries_all: list[tuple[str, str]] = []
    match_entries_conference: list[tuple[str, str]] = []
    full_to_abbr: dict[str, str] = {}

    with p.open(encoding='utf-8', newline='') as fh:
        reader = csv.reader(fh)
        next(reader, None)
        for row in reader:
            if len(row) < 2: continue
            abbr = row[0].strip()
            if len(row) >= 3:
                match_name = row[1].strip()
                full_name = row[2].strip()
            else:
                match_name = full_name = row[1].strip()
                
            if match_name and full_name:
                match_entries_all.append((match_name, full_name))
                if abbr:
                    match_entries_conference.append((match_name, full_name))
                    abbr_to_full[abbr.lower()] = full_name
                    if full_name not in full_to_abbr:
                        full_to_abbr[full_name] = abbr

    if not match_entries_all and not abbr_to_full: raise ValueError(f'No names found in {csv_path}')
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

def simplify_booktitle(raw: str, expansions: list, abbr_to_full: dict, locations_set: set[str]) -> str:
    """Simplify a CONFERENCE name for fuzzy matching."""
    # 1. Latex剥离
    text = strip_latex(raw)
    # 2. 去除所有括号和其内部的字符
    text = re.sub(r'\([^)]*\)', ' ', text)
    text = re.sub(r'\[[^\]]*\]', ' ', text)
    
    # 3. 提前统一变成小写
    text = text.lower()
    
    # 4. 按照conferences.csv中的会议缩写，仅去除带有年份后缀的缩写，保留仅有缩写的情况
    for abbr in abbr_to_full.keys():
        abbr_pattern = re.compile(
            rf"(?<![a-z0-9]){re.escape(abbr)}(?:['\u2019\-\s](?:19|20)?\d{{2}})(?![a-z0-9])"
        )
        text = abbr_pattern.sub(' ', text)
        
    # 5. 利用short.csv补全缩写 (提前执行，防止后续去噪步骤吃掉缩写尾部的标点)
    text = _apply_expansions(text, expansions)
    
    # 6. 去除各式各样的日期组合及纯月份 (不限位置，全文本捕获)
    text = _DATE_BLOCK_RE.sub(' ', text)
    
    # 7. 去除表示第几次的序数词修饰 (如 1st, 2nd, 24th)
    text = re.sub(r'\b\d+(?:st|nd|rd|th)\b', ' ', text)
    
    # 8. 去除首部的纯年份 (如 2019 ieee...)
    text = re.sub(r'^\s*(?:19|20)\d{2}[\s:,\-]*', '', text)
    
    # 9. 去掉尾部的噪音 (基于精准的逐段剥离机制)
    text = _remove_trailing_noise(text, locations_set)
    
    # 10. 去掉首部或逗号后的proceedings (on/of/the完全可选，即使无附加单词也整体去掉)
    # 注意：结尾使用 \s* 而不是 \s+，确保 "proceedings" 单独存在时也能被完全删除
    text = re.sub(r'(?:(?:^|,)\s*)proceedings(?:\s+(?:of|the|on))*\s*', '', text)

    # 11. remove : & , / -
    text = re.sub(r'[:&,/-]+', ' ', text)

    # 最终清理多余空格
    return re.sub(r'\s+', ' ', text).strip()

# ===================================================================
# Abbreviation extraction
# ===================================================================
def extract_series_abbr(text: str):
    cleaned = clean_latex(text).strip()
    if not cleaned: return None
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
    if not cleaned_value: return None, 0.0
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
    if series_abbr is not None:
        full = abbr_to_full.get(series_abbr.lower())
        if full:
            return full, 100.0, 'series'

    # 只从会议名称中提取缩写，期刊名称跳过此步骤
    if field_name in CONFERENCE_FIELDS:
        for name_abbr in extract_name_abbrs(field_value):
            full = abbr_to_full.get(name_abbr.lower())
            if full:
                return full, 100.0, 'name-abbr'

    if field_name in JOURNAL_FIELDS:
        entries = match_entries_all
        compared_as = clean_latex(field_value).lower()
        compared_as = _apply_expansions(compared_as, expansions)
        
        # 将 &, -, / 替换为空格，解体粘合的单词以提升匹配率
        compared_as = re.sub(r'[:&,/-]', ' ', compared_as)
        compared_as = re.sub(r'\s+', ' ', compared_as).strip()
    else:
        entries = match_entries_conference
        compared_as = simplify_booktitle(field_value, expansions, abbr_to_full, locations_set)

    best_full, best_score = fuzzy_match_best(compared_as, entries)
    if best_full and best_score >= threshold:
        return best_full, best_score, 'fuzzy'
        
    return None, best_score, 'below-threshold'

# ===================================================================
# BibTeX parser / transformer
# ===================================================================
def _next_entry_at(content: str, start: int) -> int:
    i = start
    while True:
        i = content.find('@', i)
        if i == -1: return -1
        if i + 1 < len(content) and (content[i + 1].isalpha() or content[i + 1] == '_'): return i
        i += 1

def _matching_brace(content: str, open_pos: int) -> int:
    depth, pos = 1, open_pos + 1
    while pos < len(content) and depth > 0:
        if content[pos] == '{': depth += 1
        elif content[pos] == '}': depth -= 1
        pos += 1
    return pos

def _read_value(inner: str, start: int):
    ch = inner[start]
    if ch == '{':
        depth, pos = 1, start + 1
        while pos < len(inner) and depth > 0:
            if inner[pos] == '{': depth += 1
            elif inner[pos] == '}': depth -= 1
            pos += 1
        return pos, inner[start:pos]
    if ch == '"':
        pos = start + 1
        while pos < len(inner) and inner[pos] != '"':
            if inner[pos] == '\\': pos += 1
            pos += 1
        return pos + 1, inner[start:pos + 1]
    pos = start
    while pos < len(inner) and inner[pos] not in ',}': pos += 1
    return pos, inner[start:pos].strip()

def _extract_series_from_inner(inner: str):
    for fname in ('series', 'collection'):
        pattern = re.compile(re.escape(fname) + r'\s*=\s*', re.IGNORECASE)
        m = pattern.search(inner)
        if m and m.end() < len(inner):
            _, raw = _read_value(inner, m.end())
            abbr = extract_series_abbr(raw)
            if abbr: return abbr
    return None

def process_bib(
    content, abbr_to_full, match_entries_all, match_entries_conference, 
    threshold, expansions, full_to_abbr, locations_set
):
    results = []
    below_entries: dict[str, list] = {}
    out: list[str] = []
    cursor = 0

    while cursor < len(content):
        entry_start = _next_entry_at(content, cursor)
        if entry_start == -1:
            out.append(content[cursor:]); break
        out.append(content[cursor:entry_start])
        brace = content.find('{', entry_start)
        if brace == -1:
            out.append(content[entry_start:]); break
        close = _matching_brace(content, brace)
        inner = content[brace + 1 : close - 1]
        comma = inner.find(',')
        if comma == -1:
            out.append(content[entry_start:close]); cursor = close; continue
        entry_key = inner[:comma].strip()
        out.append(content[entry_start : brace + 1 + comma + 1])
        series_abbr = _extract_series_from_inner(inner)
        fpos = comma + 1

        while fpos < len(inner):
            ws = fpos
            while fpos < len(inner) and inner[fpos] in ' \t\n\r': fpos += 1
            if fpos >= len(inner):
                out.append(inner[ws:]); break
            eq = inner.find('=', fpos)
            if eq == -1:
                out.append(inner[fpos:]); break
            field_name = inner[fpos:eq].strip().lower()
            out.append(inner[ws : eq + 1])
            fpos = eq + 1
            ws2 = fpos
            while fpos < len(inner) and inner[fpos] in ' \t\n\r': fpos += 1
            out.append(inner[ws2:fpos])
            if fpos >= len(inner): break
            end, raw = _read_value(inner, fpos)
            fpos = end

            if field_name in TARGET_FIELDS:
                repl, score, method = find_match(
                    raw, field_name, series_abbr, abbr_to_full, 
                    match_entries_all, match_entries_conference, threshold, expansions, locations_set
                )
                results.append({
                    'key': entry_key, 'field': field_name, 'raw': clean_latex(raw),
                    'matched': repl, 'score': round(score, 1), 'method': method
                })
                
                if repl is not None:
                    if field_name in CONFERENCE_FIELDS and repl in full_to_abbr:
                        abbr = full_to_abbr[repl]
                        out.append('{' + repl + ' (' + abbr + ')}')
                    else:
                        out.append('{' + repl + '}')
                else:
                    out.append(raw)
                    
                if repl is None:
                    if field_name in JOURNAL_FIELDS:
                        compared_as_log = clean_latex(raw).lower()
                    else:
                        compared_as_log = simplify_booktitle(raw, expansions, abbr_to_full, locations_set)
                    below_entries.setdefault(entry_key, []).append(
                        (field_name, clean_latex(raw), round(score, 1), compared_as_log)
                    )
            else:
                out.append(raw)

            ws3 = fpos
            while fpos < len(inner) and inner[fpos] in ' \t\n\r': fpos += 1
            out.append(inner[ws3:fpos])
            if fpos < len(inner) and inner[fpos] == ',':
                out.append(','); fpos += 1
        out.append(content[close - 1])
        cursor = close

    if below_entries:
        print('\n[bibclean] Entries with unmatched target fields:', file=sys.stderr)
        for key in sorted(below_entries):
            for fname, raw, score, compared_as in below_entries[key]:
                print(f" {key}: {fname} = '{raw}' (score={score}, compared-as '{compared_as}')", file=sys.stderr)
    return ''.join(out), results

