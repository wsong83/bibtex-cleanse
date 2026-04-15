"""bibtex_write.py - 将统一的字典列表序列化为 BibTeX 文本。

输出格式规范：
- 条目类型小写
- 字段名小写
- 字段严格按照字母表顺序 (a-z) 排列
- 统一使用大括号 {} 包裹字段值（兼容性最好）
"""

def format_bibtex(entries: list[dict], indent: str = "  ") -> str:
    """将 parse_bibtex 返回的字典列表格式化为 BibTeX 字符串。
    
    Args:
        entries: 字典列表，每个字典必须包含 'key' 和 'entry_type'。
        indent: 字段缩进字符串，默认为两个空格。

    Returns:
        格式化后的 BibTeX 字符串。
    """
    lines = []
    for entry in entries:
        # 弹出元数据，剩下的都是实际字段
        entry_type = entry.pop('entry_type', 'misc')
        key = entry.pop('key', 'UNKNOWN')
        
        # 核心需求：对字段按 key 进行字母排序
        sorted_fields = sorted(entry.items(), key=lambda x: x[0])
        
        lines.append(f"@{entry_type.lower()}{{{key},")
        if not sorted_fields:
            lines.append("}")
        else:
            # 计算当前条目中最长的字段名长度，用于等号对齐
            max_field_len = max(len(field) for field, _ in sorted_fields)
            
            for field, value in sorted_fields:
                # 计算需要补齐的空格数
                padding = " " * (max_field_len - len(field))
                # 统一加上外层大括号
                wrapped_value = "{" + value + "}"
                lines.append(f"{indent}{field.lower()}{padding} = {wrapped_value},")
                
            # 将最后一个字段的尾逗号去掉
            lines[-1] = lines[-1][:-1]
            lines.append("}")
            
        # 条目之间空一行
        lines.append("")
        
    return "\n".join(lines)
