---
name: book-to-knowledge
description: "将书籍和文档（PDF、EPUB、DOCX、HTML、Markdown、纯文本、RTF、MOBI/AZW）转换为结构化知识库，提取框架、思维模型、原则、技术和反模式。输出到 knowledge/<slug>/。触发词：导入知识库、导入书籍、知识库导入、学习资料、book-to-knowledge、extract、提取知识"
---

<!--
Cross-agent notes (informational; ignored by host agents):
  - Compatible skill roots: GitHub Copilot CLI (~/.copilot/skills, ~/.agents/skills,
    .github/skills, .claude/skills, .agents/skills), Amp (.agents/skills,
    ~/.config/agents/skills, ~/.config/amp/skills), Claude Code (~/.claude/skills).
  - `allowed-tools` is intentionally omitted to stay agent-neutral: Copilot CLI uses
    `shell`/MCP-server names, Claude uses `Bash`/`Read`/`Write`/`Glob`/`Grep`, Amp
    adds `shell_command`. The skill needs shell (to run extract.py) and file
    read/write — each host will prompt for those on first use.
  - Argument hint: <path-to-document-folder-or-glob>... [knowledge-slug]
  - Output goes to knowledge/<slug>/ (configurable via KNOWLEDGE_ROOT env var)
-->

# Book-to-Knowledge Converter

Transform written knowledge into structured, queryable knowledge bases by extracting structure — not producing summaries.

## Philosophy

Books contain crystallized expertise: frameworks, principles, and techniques that took years to develop. This skill extracts that knowledge into a reusable knowledge base that any AI agent can query and reference.

**Extract structure, not summaries.** A knowledge base isn't a book report. It's a toolkit of:
- Named frameworks (mental models with clear application)
- Actionable principles (rules that guide decisions)
- Techniques (step-by-step methods)
- Anti-patterns (what to avoid and why)
- Voice calibration (how the author thinks and communicates)

**Preserve the author's precision.** Frameworks often have specific names for reasons. "The 5 Whys" isn't interchangeable with "ask why multiple times." Capture the exact formulation.

**Layer depth appropriately.** Simple books → compact knowledge. Complex books with 10+ frameworks → knowledge with reference files and on-demand chapters.

---

## Modes of Operation

Four paths available. Route based on what the user asks:

### 1. Full Conversion (Default)
**Trigger:** User provides one or more document/directory/glob paths without special instructions
**Action:** Run all steps below (Steps 0–10)
**Output:** Complete knowledge base with knowledge.md, chapters/, glossary, patterns, cheatsheet, source.yaml

### 2. Analyze Only
**Trigger:** User says "analyze", "just extract", or "I want to review before generating"
**Action:** Run Steps 0–3, then produce a structured extraction report (frameworks, principles, techniques found). Stop — do NOT generate knowledge files.
**Output:** Analysis report for user review

### 3. Generate from Prior Analysis
**Trigger:** User has existing analysis notes or previously ran analyze-only
**Action:** Skip Steps 0–3, use the provided analysis as input, run Steps 4–10
**Output:** Knowledge base files from the provided analysis

### 4. Update / Fold-in (Existing Knowledge)
**Trigger:** User provides one or more new source paths and indicates they want to update an existing knowledge base (either by pointing to the existing knowledge folder, providing a slug that already exists in `KNOWLEDGE_ROOT`, or explicitly requesting an update).
**Action:** Run Step 0 (out-of-scope check), Step 1 (validate inputs), Step 1.5 (identify book type), and Step 2 (extract new files). Then skip to Step 5 (identify/detect existing knowledge path) and run the **Update / Fold-in Workflow** to merge the new content into the existing knowledge files.
**Output:** Updated existing knowledge base with new/revised chapter summaries and merged indexes/glossaries.

---

## Knowledge Locations

This converter outputs to `KNOWLEDGE_ROOT/<slug>/`. By default, `KNOWLEDGE_ROOT` is set to `./knowledge/` (a directory at the project root). Override via the `KNOWLEDGE_ROOT` environment variable:

```bash
# Default
KNOWLEDGE_ROOT="./knowledge"

# Custom
export KNOWLEDGE_ROOT="/path/to/shared/knowledge"
```

The output is plain markdown files — no agent-specific metadata. This means `book-knowledge` (the companion query skill) or any other tool can read the knowledge base regardless of the agent platform.

For the converter's own helper script (`scripts/extract.py`, `scripts/rebuild_knowledge_index.py`), this SKILL.md discovers them relative to its own location:

```bash
# extract.py is always found alongside this SKILL.md
SKILL_DIR="$(dirname "$(readlink -f "$0")")"
SCRIPT_PATH="$SKILL_DIR/scripts/extract.py"
```

---

## Step 0 — Out-of-scope check

If no arguments are provided, stop and respond:
> "book-to-knowledge requires a supported document path, folder, or glob pattern. Usage: `book-to-knowledge <path-to-document-folder-or-glob>... [knowledge-slug]`"

Throughout the workflow:
- Identify the input paths and the optional knowledge slug.
- If the last argument is not a file, folder, or glob that exists or matches any files, and it looks like a slug (e.g. lowercase hyphens, alphanumeric), treat it as `KNOWLEDGE_SLUG`.
- Treat all other arguments as the list of `INPUT_PATHS`.
- If any input path is an existing knowledge directory (contains `knowledge.md` and a `chapters/` sub-folder), or if `KNOWLEDGE_SLUG` matches an existing slug in `KNOWLEDGE_ROOT`, flag this run as an **Update/Fold-in** operation (Mode 4).

---

## Step 1 — Validate input

Verify that there is at least one supported file, directory, or glob pattern among the `INPUT_PATHS`.
For directories and globs, expand them to find matching supported files (`.pdf`, `.epub`, `.docx`, `.txt`, `.md`, `.markdown`, `.rst`, `.adoc`, `.html`, `.htm`, `.rtf`, `.mobi`, `.azw`, `.azw3`).

If no supported files are found, stop with a clear error message.

---

## Step 1.5 — Identify content type

Before extracting, ask the user:

> "What kind of content do these sources have? This helps me choose the best extraction method.
>
> 1. **Technical** — has code blocks, tables, formulas, diagrams (e.g. programming books, academic papers, architecture guides)
> 2. **Text-heavy** — mostly prose, few or no tables/code (e.g. management, productivity, narrative non-fiction)
> 3. **Not sure** — I'll use the fast method and warn you if quality seems limited"

Store the answer as `BOOK_TYPE`:
- Option 1 → `BOOK_TYPE=technical`
- Option 2 → `BOOK_TYPE=text`
- Option 3 → `BOOK_TYPE=text`

**If `BOOK_TYPE=technical`**, inform the user before proceeding:
> "📐 Technical mode selected — using Docling for structure-aware extraction (tables, code blocks, formulas preserved as markdown). This takes ~1.5s per page, so expect a few minutes for longer sources. Starting now…"

**If `BOOK_TYPE=text`**, inform:
> "📄 Text mode selected — using the fastest suitable extractor for each file type. Plain text/Markdown/HTML are usually ready in seconds; PDFs use pdftotext when available."

---

## Step 2 — Extract text from the source documents

Run the extraction script. The script is always found alongside this SKILL.md:

```bash
# Resolve script path relative to this SKILL.md
SKILL_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
SCRIPT_PATH="$SKILL_DIR/scripts/extract.py"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

"$PYTHON_BIN" "$SCRIPT_PATH" $INPUT_PATHS --mode <BOOK_TYPE> --install-missing ask
```

Before extraction, the script checks optional Python packages needed for the detected format. If a better extractor is missing, it prompts the user with the available fallback. Non-interactive sessions default to fallback unless install mode is explicitly `yes`.

**Tip — preflight the environment:** run `"$PYTHON_BIN" "$SCRIPT_PATH" --check` to print a per-format report of which extractors are installed and the exact command to install whatever is missing, without processing any file. Useful when a user reports a setup or quality problem.

This creates:
- `<tempdir>/book_skill_work/full_text.txt` — combined extracted text of all sources with clear visually demarcated boundaries.
- `<tempdir>/book_skill_work/metadata.json` — overall combined size, words, pages, token counts, and a detailed list of individual processed `sources`.

Read `<tempdir>/book_skill_work/metadata.json` to inspect the results.

---

## Step 2.5 — Pre-flight cost estimate

Read `<tempdir>/book_skill_work/metadata.json` and present the user with an estimate **before doing any generation**:

```
📖 Sources detected: <total_sources> source(s)
<list each source filename and format from the sources metadata list>
📄 Combined Pages/Sections: ~<N> | Words: ~<N> | Total tokens: ~<N>K

💰 Estimated token cost (Full Conversion / Update):
   Input  (reading + prompts): ~<N>K tokens
   Output (knowledge files generated/updated):  ~<N>K tokens
   Total:                           ~<N>K tokens

   Reference prices (as of 2025):
   Claude Sonnet 4.5 → ~$<X> USD
   Claude Haiku 4.5  → ~$<X> USD

   ⏱  Estimated time: ~<N> minutes

📁 Files to be generated/updated:
   knowledge.md + chapter files + glossary + patterns + cheatsheet + source.yaml

➡  Proceed with Full Conversion / Update? (or type "analyze only" to preview first)
```

**How to estimate:**
- Input tokens ≈ `estimated_tokens` from metadata × 1.3 (prompts overhead per chapter pass)
- Output tokens ≈ chapters × per-chapter budget + 4,000 (knowledge.md) + 4,500 (glossary + patterns + cheatsheet)
  - Per-chapter budget midpoint by `BOOK_TYPE` (DEPTH is decided later in Step 4 and can raise it): `text` ≈ 1,000, `technical` ≈ 1,800. If the user has already indicated reference-only vs deep study, use the matching row of the Step 7 matrix.
- Price: Sonnet input=$3/MTok output=$15/MTok — Haiku input=$0.80/MTok output=$4/MTok

Wait for the user to confirm before proceeding. If they say "analyze only", switch to Mode 2.

---

## Step 2.6 — REPL-style access for large books (> 50k tokens)

Inspired by the Recursive Language Model (RLM) paradigm: treat `full_text.txt` as a queryable corpus, not a single read. Loading the whole file into context burns budget you will need later for generation.

For books over ~50k tokens, prefer programmatic probes over `Read(full_text.txt)` without bounds:

```bash
# Size check before any Read
wc -w "$FULL_TEXT_PATH"

# Find chapter offsets without loading the whole file
grep -n -E "^\s*(Chapter|CHAPTER)\s+[0-9]+" "$FULL_TEXT_PATH" | head -40

# Pull only the chapter you need (lines start..end inclusive)
sed -n '<start>,<end>p' "$FULL_TEXT_PATH"

# Verify a framework is actually mentioned before claiming it in knowledge.md
grep -c -i "westrum\|dora" "$FULL_TEXT_PATH"

# Targeted Read with offset/limit avoids dumping the full file
# Read(file_path=full_text.txt, offset=<line>, limit=<lines>)
```

Use this approach for Step 3 (structure analysis), Step 7 (per-chapter summaries), and Step 8 (glossary / patterns extraction). On books under 50k tokens, a single `Read` is fine.

Why this matters: a 200-page book is ~75k tokens. Re-reading it once per chapter (28 passes) costs ~2M input tokens; using grep + sed to pull only relevant slices keeps generation cost proportional to the output, not the source.

---

## Step 3 — Analyze book structure

Read the first 8,000 characters of the extracted `full_text.txt` to identify:
- Book **title** and **author(s)**
- **Chapter structure** (look for "Chapter N", "PART I", numbered headings, table of contents)
- **Core themes** and subject domain
- Approximate number of chapters

Then read the Table of Contents section if present to map all chapters.

**If mode is "Analyze Only":** produce the extraction report now and stop. Structure:
```
## Extraction Report — <Title>

### Author's Core Frameworks
- **<Framework Name>**: <what it is and when to apply>

### Key Principles
- <Principle>: <actionable rule>

### Techniques & Methods
- <Technique>: <step-by-step or how-to>

### Anti-patterns
- <What to avoid>: <why>

### Suggested Slug
`{author-lastname}-{core-concept}` — e.g. `cialdini-influence`

### Chapters Detected
| # | Title | Main Frameworks |
```

---

## Step 4 — Ask purpose (Full Conversion only)

Before generating, ask the user:

> "What should this knowledge base help you do? (Pick one or more)
> 1. Reference the author's frameworks while working
> 2. Think with the author's mental models
> 3. Look up specific chapters and concepts
> 4. All of the above"

Use the answer to weight what gets highlighted in the knowledge.md Core section.

**Derive `DEPTH` from the answer (no extra prompt):**
- Answer is **only** option 3 (reference) → `DEPTH=reference` — lean, fast-lookup chapters.
- Answer includes option 1, 2, or 4 → `DEPTH=study` — deeper chapters with more worked detail, examples, and reasoning.

`DEPTH` and `BOOK_TYPE` together set the per-chapter token budget in Step 7. Do **not** ask a separate "study vs reference" question — it is inferred here. (In Modes 2/3, where Step 4 is skipped, default `DEPTH=study`.)

---

## Step 5 — Determine slug and output path

If `KNOWLEDGE_SLUG` was provided, use it as the slug.
Otherwise, propose two options and let the user choose:
- **By author-concept**: `{author-lastname}-{core-concept}` (e.g. `cialdini-influence`, `meadows-systems`)
- **By title**: lowercase hyphens from book title (e.g. `designing-data-intensive-apps`)

Default to author-concept format if the book has a strong methodological identity.

Determine `KNOWLEDGE_ROOT`:
1. Use `$KNOWLEDGE_ROOT` if set
2. Default to `./knowledge/` (relative to the project root)
3. If the directory doesn't exist, create it

Set `OUTPUT_DIR="$KNOWLEDGE_ROOT/<slug>"` and check if it already exists.
If it does, prompt the user to choose:
1. **Update / Fold-in** (Mode 4) — integrate new content into the existing knowledge base.
2. **Overwrite** — delete and regenerate from scratch.
3. **Rename** — append `-2` or use a different custom slug.

If the user selects **Update / Fold-in**, proceed immediately to the **Update / Fold-in Workflow** section after Step 2.5 (skipping Steps 3, 4, 6, 7, 8, 9).

---

## Step 6 — Create knowledge directory structure

```bash
mkdir -p "$OUTPUT_DIR/chapters"
```

---

## Step 7 — Generate chapter summaries

**TOKEN BUDGET RULE — CRITICAL (adaptive):**

The per-chapter budget scales with `BOOK_TYPE` and `DEPTH`. Technical chapters need room for code and tables; study depth needs room for worked reasoning. Pick the budget from this matrix:

| | `DEPTH=reference` | `DEPTH=study` |
|---|---|---|
| `BOOK_TYPE=text` | 800–1,200 tokens | 1,000–1,800 tokens |
| `BOOK_TYPE=technical` | 1,200–1,800 tokens | 2,000–3,000 tokens |

- These are per-file targets, not hard caps — a dense chapter may run over, a thin one under. Density still beats length (Quality Rule #3): never pad to hit a number.
- Files are loaded on-demand, so a larger chapter only costs tokens when that chapter is actually read.
- When in doubt between two cells (e.g. mixed-content book), use the lower budget and let depth come from precision, not volume.

**`DEPTH=study` is earned with content, not a bigger number.** The standard section template (Core Idea → Connects To) naturally lands a dense prose chapter around 700–900 tokens. To reach the study budget *honestly* — not by padding — a study-depth chapter must add concrete material:
- **Reproduce one worked example or artifact** from the chapter (e.g. the example press release, a sample dialogue, a filled-in template, a decision the author walks through) under a `## Worked Example` section. This is the single biggest lever and the main thing a learner returns for.
- **Expand the "How" of each framework** into explicit steps or criteria, not a one-liner.
- **Add a short "Why it works / failure mode" note** to the top 1–2 frameworks.

If a chapter genuinely has no worked example and resists expansion, let it land below the study floor rather than padding — and note that the chapter is thin in its Core Idea. A `reference`-depth chapter, by contrast, deliberately omits worked examples and keeps only the decision-ready essentials.

For EACH chapter/major section identified in Step 3:

Read the corresponding section of the extracted `full_text.txt` (use character offsets or grep for chapter headings).

Create `$OUTPUT_DIR/chapters/ch<NN>-<slug>.md` using the structure below.

**Adapt emphasis based on `BOOK_TYPE`:**
- `technical` → prioritize "Code Examples", "Reference Tables", and "Commands & APIs" sections; preserve exact syntax
- `text` → prioritize "Frameworks Introduced", "Mental Models", and "Key Takeaways"; skip empty technical sections

```markdown
# Chapter N: <Full Title>

## Core Idea
<1–2 sentences: the single most important thing this chapter teaches>

## Frameworks Introduced
- **<Framework Name>**: <exact formulation — preserve the author's naming>
  - When to use: <specific situation>
  - How: <steps or criteria>

## Key Concepts
- **<Term>**: <precise definition in 1 sentence>
(5–10 most important terms from this chapter)

## Mental Models
<2–4 frameworks or thinking tools. Write as "Use X when Y" or "Think of X as Y">

## Anti-patterns
- **<What to avoid>**: <why it fails>

## Code Examples *(technical books only — omit if BOOK_TYPE=text)*
<!-- Copy the most instructive snippet from the chapter. Preserve indentation exactly. -->
```<language>
<key code example from this chapter>
```
- **What it demonstrates**: <one line>

## Reference Tables *(technical books only — omit if BOOK_TYPE=text)*
<!-- Reproduce any comparison matrix, parameter table, or decision table from the chapter in markdown. -->

## Worked Example *(DEPTH=study only — omit for DEPTH=reference)*
<!-- Reproduce or reconstruct one concrete example the author works through: a
     sample document, a dialogue, a filled-in template, a before/after, or a
     decision walked end-to-end. This is what makes a study chapter worth its
     budget. Keep it faithful to the source; never copy long raw passages —
     reconstruct the example compactly. -->

## Key Takeaways
1. <Actionable insight>
2. <Actionable insight>
3. <Actionable insight>
(3–7 takeaways a practitioner must remember)

## Connects To
- **Ch N**: <why this chapter relates>
- **<Concept>**: <external concept or standard it connects with>
```

---

## Step 8 — Generate supporting files

### glossary.md
Create `$OUTPUT_DIR/glossary.md`:
- Every significant term from the book, alphabetically sorted
- Format: `**Term** — definition (Ch N)`
- Max 1,500 tokens

### patterns.md
Create `$OUTPUT_DIR/patterns.md`:
- All concrete techniques, design patterns, algorithms from the book
- Format: `## Pattern Name\n**When to use**: ...\n**How**: ...\n**Trade-offs**: ...`
- Max 2,000 tokens

### cheatsheet.md
Create `$OUTPUT_DIR/cheatsheet.md`:

**This is the most differentiated layer of the knowledge base — treat it as a reasoning aid, not a keyword list.** Anyone can grep the glossary for a term. The cheatsheet captures the author's *judgment*: the decisions they'd make and why. It's the file that turns "I know the words" into "I'd act the way the author would".

Prioritize, in order:
1. **Decision rules** — "When X, do Y, because Z." The if/then logic the author applies, stated so the reader can apply it without re-reading the book.
2. **Decision trees / flowcharts** (as nested bullets or a small table) — for choices with more than two branches.
3. **Trade-off matrices** — competing options scored on the dimensions the author cares about, so the reader can pick under their own constraints.
4. **Thresholds & defaults** — the specific numbers, ratios, or rules of thumb the author commits to (e.g. "keep functions under ~20 lines", "alert when error budget < 10%").
5. **Tells & smells** — fast heuristics for recognizing a situation ("if you see X, you're probably in trouble Y").

Avoid: bare term→definition rows (that's the glossary), and prose paragraphs (that's the chapters). Every line should help the reader *decide* something.

- Format mostly as compact tables and decision rules; the content you'd want on a single printed page kept beside you while working.
- Max 1,200 tokens.

---

## Step 9 — Generate the master knowledge.md

**CRITICAL TOKEN BUDGET: Keep knowledge.md body under 4,000 tokens.**
Compaction truncates from the END — put the most important content FIRST.

Create `$OUTPUT_DIR/knowledge.md`:

```markdown
# <Full Title> — 知识库
**作者**: <Author(s)> | **章节**: <N> | **生成日期**: <YYYY-MM-DD>

## 核心框架
<!-- ~2,000 tokens: the author's most important named frameworks and principles.
     Preserve exact names. Write as "Use X when Y", "Prefer X over Y because Z".
     This is a toolkit, not a summary. -->

<generate 2,000 tokens of the most critical frameworks and insights here>

---

## 章节索引

| # | 标题 | 关键框架 |
|---|------|---------|
| [ch01](chapters/ch01-<slug>.md) | <Title> | <framework1>, <framework2> |
| [ch02](chapters/ch02-<slug>.md) | <Title> | <framework1>, <framework2> |
...

## 主题索引

<!-- Alphabetical. Major terms/frameworks → chapter(s) that cover them. -->
- **<Term>** → ch<N>[, ch<N>]

## 辅助文件

- [glossary.md](glossary.md) — 术语表
- [patterns.md](patterns.md) — 叙事模式与技法
- [cheatsheet.md](cheatsheet.md) — 决策速查
```

Note: unlike agent skill SKILL.md files, knowledge.md uses plain markdown with no YAML frontmatter. This makes it directly readable by any tool, agent, or human without platform-specific parsing.

---

## Step 10 — Generate source metadata and rebuild index

### 10a — Generate source.yaml

Create `$OUTPUT_DIR/source.yaml` with the original source metadata:

```yaml
# knowledge/<slug>/source.yaml
knowledge_version: "1.0"
slug: "<slug>"
title: "<Full Title>"
author: "<Author(s)>"
source_format: "<epub|txt|pdf|...>"
word_count: <N>
chapter_count: <N>
generated_date: "<YYYY-MM-DD>"
tags: ["<tag1>", "<tag2>"]
content_type: "<text|technical>"
```

### 10b — Rebuild knowledge index

Run the index rebuild script:

```bash
SKILL_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

"$PYTHON_BIN" "$SKILL_DIR/scripts/rebuild_knowledge_index.py" \
  --knowledge-root "$KNOWLEDGE_ROOT"
```

This scans `$KNOWLEDGE_ROOT/*/source.yaml` and writes `$KNOWLEDGE_ROOT/index.yaml`.

### 10c — Cleanup temp files

```bash
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

"$PYTHON_BIN" - <<'PY'
import os
import shutil
import tempfile
from pathlib import Path
shutil.rmtree(
    os.environ.get("BOOK_SKILL_WORKDIR", Path(tempfile.gettempdir()) / "book_skill_work"),
    ignore_errors=True,
)
PY
```

### 10d — Report

```
✅ Knowledge base created: $OUTPUT_DIR/

📚 Book: <Full Title> — <Author>
📄 Chapters: <N>

Files generated:
  knowledge.md      — core frameworks + index   (~X tokens)
  source.yaml       — source metadata
  chapters/         — <N> chapter summaries     (~X tokens each, ~X total)
  glossary.md       — key terms                 (~X tokens)
  patterns.md       — techniques & patterns     (~X tokens)
  cheatsheet.md     — quick reference           (~X tokens)
  ─────────────────────────────────────────────────────
  Total: ~X tokens (loaded on-demand, not all at once)

Usage:
  book-knowledge load <slug>            → load core frameworks
  book-knowledge query <slug> <topic>   → find and explain a topic
  book-knowledge chapter <slug> ch<N>   → dive into a specific chapter
```

---

## Update / Fold-in Workflow

When performing an Update/Fold-in operation on an existing knowledge base at `$OUTPUT_DIR/`:

### 1. Read Existing Structure
Read and parse the existing knowledge files:
- Read `$OUTPUT_DIR/knowledge.md` to parse the existing **Chapter Index**, **Topic Index**, metadata (author, total chapters), and **Core Frameworks**.
- List all files in `$OUTPUT_DIR/chapters/` to find the highest chapter number (e.g. `ch12`).
- Read `$OUTPUT_DIR/glossary.md`, `$OUTPUT_DIR/patterns.md`, and `$OUTPUT_DIR/cheatsheet.md` to see what terms and frameworks are already indexed.

### 2. Match Content & Identify Revisions vs. Additions
Analyze the new extracted text in `<tempdir>/book_skill_work/full_text.txt` to identify if the new content represents:
- **Updates/Revisions to existing chapters**: If a section of the new content directly updates or expands an existing chapter's topic, read the existing chapter file, merge the new details into it, and rewrite the file.
- **New additions**: If the content introduces new chapters, papers, or separate sections, create **new chapter summary files** under `chapters/`. Start numbering these files after the highest existing chapter number (e.g. if the existing chapters stop at `ch12`, create `ch13-*.md`, `ch14-*.md`, etc.).

### 3. Generate or Update Chapter Summary Files
For each new or revised chapter:
- Read the corresponding section of the extracted new text.
- Follow the formatting guidelines in **Step 7** to build the summary.
- Write/update the file in `$OUTPUT_DIR/chapters/`.

### 4. Merge Supporting Files
- **Merge glossary.md**:
  - Read the existing `$OUTPUT_DIR/glossary.md`.
  - Extract all new terms and definitions from the new content (Step 8 glossary guidelines).
  - Combine and alphabetize the list of existing and new terms.
  - If a term already exists, append the new chapter/source references to it (e.g. `**Term** — definition (Ch 4, Ch 13)`).
  - Rewrite `$OUTPUT_DIR/glossary.md` with the fully merged, alphabetized list.
- **Merge patterns.md**:
  - Read existing `$OUTPUT_DIR/patterns.md`.
  - Extract any new techniques, algorithms, or patterns from the new content.
  - Append the new patterns, ensuring consistent formatting, and keeping the total length concise (under 2,500 tokens).
- **Merge cheatsheet.md**:
  - Read existing `$OUTPUT_DIR/cheatsheet.md`.
  - Extract new comparison rules, decision tables, or parameter guides.
  - Integrate them cleanly into the cheatsheet structure.

### 5. Re-generate the Master knowledge.md
Update the master knowledge file `$OUTPUT_DIR/knowledge.md`:
- **Metadata**: Increment the chapter count, update the estimated page count, and add the new source names if appropriate. Update the `Generated` date to the current date.
- **Core Frameworks**: Fold in the most high-impact mental models or principles from the new content (ensuring the overall file remains under 4,000 tokens).
- **Chapter Index**: Append the new chapters to the index table, linking to the newly created files.
- **Topic Index**: Merge the new topics alphabetically. If an existing topic is also covered in the new chapters, append the new chapter links to its line (e.g. `- **Topic** → ch05, ch13`).

### 6. Proceed to Step 10
Once the files are successfully written and merged, skip to **Step 10** to generate source.yaml, rebuild the index, cleanup, and print an update report summarizing the newly added chapters, merged glossary terms, and updated indices.

---

## Quality Rules

1. **Extract structure, not summaries** — capture named frameworks, exact formulations, anti-patterns; not chapter recaps
2. **Preserve the author's precision** — "The 5 Whys" ≠ "ask why multiple times"; keep exact naming
3. **Density over completeness** — a 1,000-token summary beats a 10,000-token excerpt
4. **Practitioner voice** — write "Use X when Y", not "The book explains X"
5. **Front-load knowledge.md** — compaction keeps the first 4,000 tokens; most important content comes first
6. **Chapter files are on-demand** — they don't count against token budget until loaded
7. **Never copy raw book text** — always synthesize, summarize, extract signal
8. **Topic index is critical** — it's how the query tool navigates to the right chapter file
