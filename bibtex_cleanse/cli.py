import argparse
import sys
from pathlib import Path
from importlib.resources import files

from .cleanse import load_conferences, load_locations, load_expansions, process_bib, TARGET_FIELDS
from .bibtex_write import format_bibtex # 导入写回模块

# ===================================================================
# CLI
# ===================================================================
def main() -> None:
    # 包内 data 目录的绝对路径（随安装位置走，不受 cwd 影响）
    _data_dir = files("bibtex_cleanse") / "data"

    parser = argparse.ArgumentParser(description='Standardise conference/journal names in BibTeX.')
    parser.add_argument('-f', '--conferences', default=str(_data_dir / 'conferences.csv'), help='3-column CSV (abbr, match name, full name)')
    parser.add_argument('-c', '--city', default=str(_data_dir / 'city.csv'), help='Location database CSV (Type, Name)')
    parser.add_argument('-s', '--short', default=str(_data_dir / 'short.csv'), help='Abbreviation expansion rules (short.csv)')
    parser.add_argument('-i', '--input', required=True)
    parser.add_argument('-o', '--output', required=True)
    parser.add_argument('-t', '--threshold', type=float, default=80.0, help='Min score 0-100 (default: 80)')
    parser.add_argument('--reorder', action='store_true',
                        help='Sort fields alphabetically (default: keep original order)')
    args = parser.parse_args()

    try:
        abbr_to_full, match_all, match_conf, full_to_abbr = load_conferences(args.conferences)
    except (FileNotFoundError, ValueError) as exc:
        print(f'Error: {exc}', file=sys.stderr); sys.exit(1)

    try:
        locations_set = load_locations(args.city)
    except FileNotFoundError as exc:
        print(f'Error: {exc}', file=sys.stderr); sys.exit(1)

    try:
        expansions = load_expansions(args.short)
    except (FileNotFoundError, ValueError) as exc:
        print(f'Error: {exc}', file=sys.stderr); sys.exit(1)

    try:
        if not Path(args.input).is_file():
            raise FileNotFoundError(f"Input file not found: {args.input}")
    except (FileNotFoundError, ValueError) as exc:
        print(f'Error: {exc}', file=sys.stderr); sys.exit(1)

    print(f'[bibclean] {len(match_all)} match entries, {len(abbr_to_full)} csv abbreviations, '
          f'{len(expansions)} expansion rules, {len(locations_set)} locations loaded', file=sys.stderr)
    print(f"[bibclean] target: {', '.join(sorted(TARGET_FIELDS))}", file=sys.stderr)
    print(f'[bibclean] threshold = {args.threshold}', file=sys.stderr)

    entries, results = process_bib(
        args.input, abbr_to_full, match_all, match_conf, args.threshold,
        expansions, full_to_abbr, locations_set
    )

    n_total = len(results)
    n_replaced = sum(1 for r in results if r['matched'] is not None)
    avg_score = sum(r['score'] for r in results) / n_total if n_total else 0.0
    print(f'\n[bibclean] done: {n_total} target field(s) checked, {n_replaced} replaced, '
          f'{n_total - n_replaced} kept, average score {avg_score:.1f}.', file=sys.stderr)

    output_content = format_bibtex(entries, reorder=args.reorder)
    Path(args.output).write_text(output_content, encoding='utf-8')
    
    print(f'[bibclean] output written to {args.output}', file=sys.stderr)

if __name__ == '__main__':
    main()

