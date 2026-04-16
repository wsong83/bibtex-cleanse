"""bibtex_write.py - 将统一的字典列表序列化为 BibTeX 文本。
输出格式规范：
- 条目类型小写
- 字段名小写
- 默认保留原始字段顺序（可通过 reorder 参数开启字母排序）
- 字段基于最长字段名进行 = 号对齐
- 统一使用大括号 {} 包裹字段值（兼容性最好）
"""

def format_bibtex(entries: list[dict], indent: str = "  ", reorder: bool = False) -> str:
    """将 parse_bibtex 返回的字典列表格式化为 BibTeX 字符串。
    Args:
        entries: 字典列表，每个字典必须包含 'key' 和 'entry_type'。
        indent: 字段缩进字符串，默认为两个空格。
        reorder: 是否按字母表顺序重新排列字段。默认为 False 保留原顺序。
    Returns:
        格式化后的 BibTeX 字符串。
    """
    lines = []
    for entry in entries:
        # 使用 copy 避免修改原始字典（pop 是原地操作）
        entry_copy = dict(entry)
        entry_type = entry_copy.pop('entry_type', 'misc')
        key = entry_copy.pop('key', 'UNKNOWN')

        # 根据 reorder 决定是否排序
        if reorder:
            fields_to_write = sorted(entry_copy.items(), key=lambda x: x[0])
        else:
            fields_to_write = list(entry_copy.items())

        lines.append(f"@{entry_type.lower()}{{{key},")
        if not fields_to_write:
            lines.append("}")
        else:
            max_field_len = max(len(field) for field, _ in fields_to_write)
            for field, value in fields_to_write:
                padding = " " * (max_field_len - len(field))
                
                # 月份字段不加花括号，直接输出三字母小写
                if field == 'month':
                    lines.append(f"{indent}{field.lower()}{padding} = {value},")
                else:
                    wrapped_value = "{" + value + "}"
                    lines.append(f"{indent}{field.lower()}{padding} = {wrapped_value},")                

            # lines[-1] = lines[-1][:-1] do not remvoe the final comma
            lines.append("}")
        lines.append("")
    return "\n".join(lines)
