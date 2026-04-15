#!/usr/bin/env python3
""" bibtex-parse.py - 统一的 BibTeX 解析模块。
自动检测最佳可用的解析后端：
  1. bibtexparser >= 2.0（优先）
  2. 内置自定义解析器（无外部依赖的回退方案，且完美保留字段原顺序）

统一接口: parse_bibtex(filepath) -> list[dict]
每个字典包含:
- 'key': 引用键（字符串）
- 'entry_type': 条目类型，小写（字符串）
- 其他字段以小写键名保存（字符串值，已去除首尾空白）
"""

import re
import sys

# ==================== 后端检测 ====================
# 检测 bibtexparser 是否可用及其版本，决定使用哪个后端。
# _BACKEND 取值: 'v2', 'builtin'
# 注意：不再支持 bibtexparser 1.x，因为其内部字段顺序会导致原格式倒序
_BACKEND = 'builtin'

try:
    import bibtexparser
    _ver_str = getattr(bibtexparser, '__version__', '0.0')
    _ver_parts = []
    for ch in _ver_str:
        if ch.isdigit():
            _ver_parts.append(ch)
        elif _ver_parts and len(_ver_parts) < 2:
            _ver_parts.append('.')
    _ver_str_clean = ''.join(_ver_parts) or '0.0'
    try:
        _major, _minor = (int(x) for x in _ver_str_clean.split('.')[:2])
    except (ValueError, IndexError):
        _major, _minor = 0, 0
    if _major >= 2:
        _BACKEND = 'v2'
    # 如果是 1.x 版本，什么都不做，保持 _BACKEND = 'builtin'
except ImportError:
    pass
except Exception:
    pass

# ==================== 内置自定义解析器 ====================
def _find_closing_brace(text, start):
    """从 text[start]（应为 '{'）向后扫描，找到匹配的 '}' 的索引。
    维护嵌套深度计数器，depth 归零时即为匹配位置。
    """
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return i
    return len(text) - 1

def _parse_value(text, start):
    """从 text[start] 解析一个 BibTeX 字段值。
    支持: {braced}, "quoted", unquoted_token, val1 # val2 拼接。
    返回 (value_str, next_index)。
    """
    i = start
    n = len(text)
    parts = []
    while i < n:
        while i < n and text[i] in ' \t\n\r':
            i += 1
        if i >= n:
            break
        if text[i] == '{':
            close = _find_closing_brace(text, i)
            parts.append(text[i + 1:close])
            i = close + 1
        elif text[i] == '"':
            j = i + 1
            while j < n and text[j] != '"':
                if text[j] == '\\':
                    j += 1
                j += 1
            parts.append(text[i + 1:j])
            i = j + 1
        else:
            m = re.match(r'[^\s,{}"#]+', text[i:])
            if m:
                parts.append(m.group())
                i += len(m.group())
            else:
                break
        j = i
        while j < n and text[j] in ' \t\n\r':
            j += 1
        if j < n and text[j] == '#':
            i = j + 1
        else:
            break
    return ''.join(parts), i

def _parse_entry_fields(content):
    """解析所有 field = value 对。返回 {field_name: value_str}（键名小写）。"""
    fields = {}
    i = 0
    n = len(content)
    while i < n:
        while i < n and content[i] in ' \t\n\r,':
            i += 1
        if i >= n:
            break
        m = re.match(r'([A-Za-z][A-Za-z0-9_-]*)\s*=\s*', content[i:])
        if not m:
            depth = 0
            while i < n:
                if content[i] == '{':
                    depth += 1
                elif content[i] == '}':
                    depth -= 1
                elif content[i] == ',' and depth == 0:
                    break
                i += 1
            continue
        field_name = m.group(1).lower()
        i += m.end()
        value, i = _parse_value(content, i)
        fields[field_name] = value.strip()
    return fields

def _parse_bibtex_builtin(filepath):
    """内置 BibTeX 解析器 — 无外部依赖，完美保留原始字段顺序。"""
    with open(filepath, encoding='utf-8') as f:
        content = f.read()
    entries = []
    i = 0
    n = len(content)
    while i < n:
        at = content.find('@', i)
        if at == -1:
            break
        i = at
        m = re.match(r'@([A-Za-z]+)\s*\{', content[i:])
        if not m:
            i += 1
            continue
        entry_type = m.group(1).lower()
        brace_open = i + m.end() - 1
        brace_close = _find_closing_brace(content, brace_open)
        body = content[brace_open + 1:brace_close]
        i = brace_close + 1
        if entry_type in ('string', 'preamble', 'comment'):
            continue
        key_m = re.match(r'\s*([^,\s]+)\s*,', body)
        if not key_m:
            continue
        key = key_m.group(1).strip()
        fields = _parse_entry_fields(body[key_m.end():])
        fields['key'] = key
        fields['entry_type'] = entry_type
        entries.append(fields)
    return entries

# ==================== bibtexparser 2.x 后端 ====================
def _parse_bibtex_v2(filepath):
    """使用 bibtexparser >= 2.0 API 解析。"""
    import bibtexparser
    library = bibtexparser.parse_file(filepath)
    entries = []
    for entry in library.entries:
        fields = { k.lower(): v.value.strip() for k, v in entry.fields_dict.items() }
        fields['key'] = entry.key
        fields['entry_type'] = entry.entry_type
        entries.append(fields)
    return entries

# ==================== 统一公共 API ====================
def parse_bibtex(filepath):
    """解析 BibTeX 文件，返回统一格式的条目字典列表。
    自动选择最佳可用后端：
    - bibtexparser >= 2.0（若已安装）
    - 内置解析器（回退方案，无外部依赖，保留原始字段顺序）
    
    Args:
        filepath: .bib 文件的路径。
    Returns:
        字典列表，每个字典包含：
        'key' (str): 引用键
        'entry_type' (str): 条目类型（小写）
        以及所有其他字段，键名小写（str 值）。
    """
    if _BACKEND == 'v2':
        return _parse_bibtex_v2(filepath)
    else:
        return _parse_bibtex_builtin(filepath)

def get_backend_name():
    """返回当前使用的解析后端名称: 'v2' 或 'builtin'。"""
    return _BACKEND
