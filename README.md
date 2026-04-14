# Bibtex Cleanse

`bibtex-cleanse` standardizes messy BibTeX entries using a rigorous **three-tier matching strategy** and a **pipeline for deep text simplification**.

There are two major useages for this tool:
1. It can be used to normalize the bibtex entries for a paper publication.
2. It can be used as a pre-cleanse for the bibtex being read as metadata for a local knowledge library (smart agent).

For example, the following bibtex entries:
~~~
@InProceedings{Bhatla2025,
  author    = {Anubhav Bhatla and Hari Rohit Bhavsar and Sayandeep Saha and Biswabandan Panda},
  booktitle = {USENIX Security Symposium},
  title     = {{SoK}: So, You Think You Know All About Secure Randomized Caches?},
  month     = aug,
  year      = {2025},
}

@InProceedings{Seznec1993,
  author    = {A. Seznec},
  booktitle = {Proc. 20th Annual Int. Computer Architecture Symp.},
  title     = {A case For Two-way Skewed-associative Caches},
  pages     = {169--178},
  month     = may,
  year      = {1993},
}

@InProceedings{Dumitras2003,
  author    = {Tudor Dumitra{\c{s}} and Radu M{\u{a}}rculescu},
  booktitle = {Proceedings of the Design, Automation and Test in Europe Conference and Exposition},
  title     = {On-Chip Stochastic Communication},
  pages     = {10790--10795},
  publisher = {{IEEE} Computer Society},
  month     = mar,
  year      = {2003},
}

@InProceedings{Tice2014,
  author    = {Caroline Tice and Tom Roeder and Peter Collingbourne and Stephen Checkoway and {\'{U}}lfar Erlingsson and Luis Lozano and Geoff Pike},
  booktitle = {Proceedings of the 23rd {USENIX} Security Symposium, San Diego, CA, USA, August 20-22, 2014.},
  title     = {Enforcing Forward-Edge Control-Flow Integrity in {GCC} {\&} {LLVM}},
  month     = aug,
  year      = {2014},
}
~~~

Will be cleansed into:

~~~
@InProceedings{Bhatla2025,
  author    = {Anubhav Bhatla and Hari Rohit Bhavsar and Sayandeep Saha and Biswabandan Panda},
  booktitle = {USENIX Security Symposium (USENIX Security)},
  title     = {{SoK}: So, You Think You Know All About Secure Randomized Caches?},
  month     = aug,
  year      = {2025},
}

@InProceedings{Seznec1993,
  author    = {A. Seznec},
  booktitle = {International Symposium on Computer Architecture (ISCA)},
  title     = {A case For Two-way Skewed-associative Caches},
  pages     = {169--178},
  month     = may,
  year      = {1993},
}

@InProceedings{Dumitras2003,
  author    = {Tudor Dumitra{\c{s}} and Radu M{\u{a}}rculescu},
  booktitle = {Design, Automation \& Test in Europe Conference (DATE)},
  title     = {On-Chip Stochastic Communication},
  pages     = {10790--10795},
  publisher = {{IEEE} Computer Society},
  month     = mar,
  year      = {2003},
}

@InProceedings{Tice2014,
  author    = {Caroline Tice and Tom Roeder and Peter Collingbourne and Stephen Checkoway and {\'{U}}lfar Erlingsson and Luis Lozano and Geoff Pike},
  booktitle = {USENIX Security Symposium (USENIX Security)},
  title     = {Enforcing Forward-Edge Control-Flow Integrity in {GCC} {\&} {LLVM}},
  pages     = {941--955},
  month     = aug,
  year      = {2014},
}

~~~

## How to Use

### 1. Command Line Interface (CLI)
The easiest way to use `bibtex-cleanse` is through the terminal. 

**Basic Usage:**
If your default CSV data files are discoverable, you only need to specify the input and output files:
```bash
bibtex-cleanse -i references.bib -o cleaned_references.bib
```
**Advanced Usage:**
If you have custom CSV databases or want to adjust the matching sensitivity, use the optional flags:
```bash
bibtex-cleanse \
  -f /path/to/my_conferences.csv \
  -c /path/to/my_cities.csv \
  -s /path/to/my_abbreviations.csv \
  -i references.bib \
  -o cleaned_references.bib \
  -t 75.0
```
**Arguments Reference:**
| Argument | Shorthand | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `--input` | `-i` | **Yes** | - | Path to the input `.bib` file. |
| `--output` | `-o` | **Yes** | - | Path where the cleaned `.bib` file will be written. |
| `--conferences` | `-f` | No | `data/conferences.csv` | Path to the 3-column conference/journal standard name database. |
| `--city` | `-c` | No | `data/city.csv` | Path to the 2-column city/location dictionary (used for noise removal). |
| `--short` | `-s` | No | `data/short.csv` | Path to the 2-column abbreviation expansion rules. |
| `--threshold` | `-t` | No | `80.0` | Minimum fuzzy match score (0.0 - 100.0). Lower values increase recall but may cause false positives. |
> **Note on Output:** The cleaned BibTeX content is written to the `-o` file. All statistical summaries, loading logs, and warnings about unmatched entries are printed to `stderr`, so they won't interfere if you pipe the output.
---

### 2. Python API
If you want to integrate `bibtex-cleanse` into another Python script (e.g., an automated paper downloading pipeline), you can use it as a library:

```python
from bibtex_cleanse import load_conferences, load_locations, load_expansions, process_bib
# 1. Load the external databases
abbr_to_full, match_all, match_conf, full_to_abbr = load_conferences("data/conferences.csv")
locations_set = load_locations("data/city.csv")
expansions = load_expansions("data/short.csv")
# 2. Read your BibTeX file
with open("input.bib", "r", encoding="utf-8") as f:
    bib_content = f.read()
# 3. Process the content
new_content, results = process_bib(
    content=bib_content,
    abbr_to_full=abbr_to_full,
    match_entries_all=match_all,
    match_entries_conference=match_conf,
    threshold=80.0,
    expansions=expansions,
    full_to_abbr=full_to_abbr,
    locations_set=locations_set
)
# 4. Inspect the results programmatically
for r in results:
    if r['matched'] is None:
        print(f"Failed to match: {r['key']} -> {r['field']} = '{r['raw']}' (Score: {r['score']})")
    else:
        print(f"Matched: {r['key']} -> {r['matched']} via [{r['method']}]")
# 5. Save the output
with open("output.bib", "w", encoding="utf-8") as f:
    f.write(new_content)
```
**The `results` object** is a list of dictionaries containing detailed matching metadata for every target field found:
- `key`: The BibTeX citation key (e.g., `Bhatla2025`).
- `field`: The field name processed (e.g., `booktitle`).
- `raw`: The original cleaned text.
- `matched`: The standardized full name (or `None` if unmatched).
- `score`: The matching score (0-100).
- `method`: How it was matched (`'series'`, `'name-abbr'`, `'fuzzy'`, or `'below-threshold'`).


## Field Classification
The tool specifically targets four BibTeX fields, divided into two categories with distinct output conventions:
- **Journal Fields** (`journal`, `journaltitle`): Replaced with the standard **Full Name** only.
- **Conference Fields** (`booktitle`, `conference`): Replaced with **Full Name (ABBR)** format (e.g., `International Conference on Machine Learning (ICML)`).

## The Three-Tier Matching Strategy
When a target field is encountered, the engine attempts to match it in descending priority:
| Priority | Strategy | Score | Scope | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 1** | Series Lookup | 100.0 | Both | Extracts the abbreviation from the entry's `series` or `collection` field and performs an exact dictionary lookup. |
| **Tier 2** | Name Extraction | 100.0 | Conferences only | Uses Regex to extract candidate abbreviations directly from the field value (e.g., words inside parentheses, or capitalized words followed by a year like `ICML 2023`) and looks them up. |
| **Tier 3** | Fuzzy Matching | 0–100 | Both | If Tiers 1 & 2 fail, the text is deeply simplified and compared against the database using weighted algorithms. Triggers if the score meets the threshold (default: 80). |

## Deep Text Simplification Pipeline
To maximize fuzzy match accuracy, the tool applies different cleaning depths depending on the field type:

### For Journals (Light Cleaning)
1. Strip LaTeX commands (`\textbf`, etc.) and resolve escape characters (`\&` → `&`).
2. Convert to lowercase.
3. Apply abbreviation expansions (e.g., `Proc.` → `Proceedings` via `short.csv`).
4. Normalize separators (`&`, `-`, `/` → spaces).

### For Conferences (Deep Cleaning)
Conferences contain heavy noise (dates, locations, proceedings prefixes). The engine applies a sequential pipeline:
1. **LaTeX & Bracket Stripping**: Removes all `{}`, `\` commands, `()`, and `[]`.
2. **Lowercasing**: Standardizes case.
3. **Known Abbreviation Stripping**: Removes known conference abbreviations *only* if they are attached to a year (e.g., removes `ICML 2023` but preserves standalone `ICML`).
4. **Expansion**: Applies `short.csv` rules early to prevent trailing punctuation from being swallowed by later steps.
5. **Date Annihilation**: Uses a massive compound Regex (`_DATE_BLOCK_RE`) to remove complex date formats anywhere in the string (e.g., `September 14-16, 2006`, `19-23 June`, `May 2005`).
6. **Ordinal Removal**: Strips `1st`, `2nd`, `24th`, etc.
7. **Leading Year Removal**: Strips years at the very beginning of the string.
8. **Trailing Noise Stripping**: A precise token-by-token mechanism (`_remove_trailing_noise`) that iteratively strips trailing commas followed by: pure years, city/country names (via `city.csv`), pure date ranges (e.g., `19-23`), and standalone month words.
9. **Prefix Removal**: Strips `Proceedings of/the/on`.
10. **Final Sanitization**: Strips remaining punctuation (`:`, `&`, `,`, `/`, `-`) and collapses whitespace.

## Fuzzy Scoring Algorithm
For Tier 3 matching, `bibtex-cleanse` uses `rapidfuzz` with a custom weighted formula to balance subset matching, substring matching, and exact order matching:
$$ \text{Score} = (0.2 \times \text{token\_set\_ratio}) + (0.3 \times \text{partial\_ratio}) + (0.5 \times \text{token\_sort\_ratio}) $$
- **`token_set_ratio` (20%)**: Matches intersecting words regardless of order or missing words.
- **`partial_ratio` (30%)**: Matches the best contiguous substring.
- **`token_sort_ratio` (50%)**: Matches words after sorting them alphabetically (highest weight to ensure strict word matching).

## State-Machine BibTeX Parser
Instead of relying on external libraries like `bibtexparser`, `bibtex-cleanse` uses a lightweight, custom state-machine parser. It scans for `@`, matches nested braces `{}`, and reads field values. This ensures:
- **Format Preservation**: Non-target fields, comments, and exact whitespace formatting are left completely untouched.
- **Robustness**: Can handle nested braces inside field values without breaking.
