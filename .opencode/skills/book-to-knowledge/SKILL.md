---
name: book-to-knowledge
description: "Convert books and documents (PDF, EPUB, DOCX, HTML, Markdown, plain text, RTF, MOBI/AZW) into structured knowledge bases by extracting frameworks, mental models, principles, techniques, and anti-patterns. Output to knowledge/<slug>/. Triggers: import book, knowledge base, extract, book-to-knowledge"
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

**Optional parameter — `--chapter-range <start>-<end>`**:
Declares the chapter number range that the input files cover. When provided in an Update/Fold-in operation, this skips the text-based "revision vs addition" analysis in Step 2 of the Update workflow, and uses the declared range directly for numbering new chapter files.

```bash
# Example: import vol-2 as chapters 101-250
book-to-knowledge vol-2.epub my-novel --chapter-range 101-250

# Example: revision pass for vol-1 (replaces existing chapters 1-100)
book-to-knowledge vol-1-revised.epub my-novel --chapter-range 1-100 --revision
```

Use `--revision` together with `--chapter-range` to mark the content as an update to existing chapters rather than new additions.

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

Wait for the user to confirm before proceeding:
- If they say "analyze only" or similar: switch to Mode 2, then proceed to Step 3.
- If they say "proceed", "yes", "full conversion", or similar: continue in Mode 1, then proceed to Step 3.
- If they indicate updating an existing knowledge base: switch to Mode 4, then proceed to Step 5.

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

**Auto-chunking for very large texts (500K+ tokens):**
When the extracted text exceeds ~60K tokens, `extract.py` automatically splits it into ~50K-token chunks saved under `full_text.chunks/` with a `manifest.json`. Use the manifest to locate which chunk contains your target chapter:

```bash
# Read manifest to find the right chunk
cat "$OUTPUT_DIR/full_text.chunks/manifest.json"

# Read a specific chunk
cat "$OUTPUT_DIR/full_text.chunks/chunk-001.txt"

# Grep within a chunk instead of the full file
grep -n "Chapter 150" "$OUTPUT_DIR/full_text.chunks/chunk-003.txt"
```

This avoids loading the entire multi-megabyte text when only a few chapters are needed for Step 7 generation.

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

**If mode is Full Conversion (Mode 1):** Proceed to Step 4.
**If mode is Analyze Only (Mode 2):** Stop here — the extraction report is the final output.

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
mkdir -p "$OUTPUT_DIR/glossary"
mkdir -p "$OUTPUT_DIR/patterns"
mkdir -p "$OUTPUT_DIR/cheatsheet"
# For books organized in volumes (e.g. 1000+ chapter novels), create per-volume
# subdirectories so each volume's files are grouped together:
# mkdir -p "$OUTPUT_DIR/chapters/vol-01"
# mkdir -p "$OUTPUT_DIR/chapters/vol-02"
# ...
```

Create all four subdirectories up front so the generation steps don't need to
check for their existence later.  This also acts as a visual reminder that all
four auxiliary file layers (glossary, patterns, cheatsheet) are mandatory.

---

## Step 7 — Generate chapter summaries

### 7a — Choose generation mode (large chapter count branch)

If `chapters_detected` from Step 2's metadata exceeds 200, enter **extra-large chapter mode** and prompt the user to choose a strategy:

```
<N> chapters detected. Recommended: volume-level aggregation.
Estimated 80% token savings vs full generation.
Volume overviews + key chapter deep-dives. Chapter-level search still works.
Choose: (A) Volume aggregation / (B) Sparse sampling / (C) Full generation?
If A: How many key chapters per volume? (default: auto ~10% of volume chapters, range 5-30)
```

**A. Volume aggregation (recommended)**
- Generate a per-volume summary file: `vol-<VV>-<slug>.md` for each volume (placed directly in `chapters/`, e.g. `chapters/vol-01-七玄门风云.md`), covering the volume's overall narrative arc, key events, and major frameworks.
- Group consecutive chapters into batch summary files (typically 8–15 chapters per batch, no more than 30). Each batch gets ONE `.md` file.
  - **Filename convention**: `ch-<NNNN>-<NNNN>-<short-title>.md` where both start and end chapter numbers are **4-digit zero-padded** (e.g. `ch-0001-0010-山边小村到入门.md`, not `ch-1-10-....md` or `ch001-010-....md`).
  - Place batch files under `chapters/vol-<VV>/` (e.g. `chapters/vol-01/ch-0001-0010-山边小村到入门.md`).
- Select key chapters per volume for full single-chapter summaries. Default calculation: `max(5, min(30, round(volume_chapters × 0.10)))`. User can override with a specific number. These chapters are identified by significance of frameworks introduced or plot milestones.
- **DEPTH applies**: The key chapter summaries use the `DEPTH` determined in Step 4. If `DEPTH=study`, include worked examples and expanded framework details; if `DEPTH=reference`, keep lean with only decision-ready essentials.
- For remaining chapters, record only the title + 1-2 sentence core event + framework tags (stored in `chapters/index.md`, no separate `.md` file).

**B. Sparse sampling**
- Let the user specify a sampling density (e.g. "every 10th chapter", "first 50 + last 50 + key plot milestones").
- Only sampled chapters get full summaries; the rest get title + key event + framework tags (stored in `chapters/index.md`).

**C. Full generation (not recommended)**
- Follow the standard per-chapter generation path below for every chapter. Warn the user about estimated time and cost before proceeding.

If chapters ≤ 200, proceed directly to the standard per-chapter generation without prompting.

### 7b — Per-chapter generation (standard mode)

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

Create `$OUTPUT_DIR/chapters/ch-<NNNN>-<slug>.md` (or `$OUTPUT_DIR/chapters/vol-<VV>/ch-<NNNN>-<slug>.md` when using volume subdirectories) using the structure below.

**Adapt emphasis based on `BOOK_TYPE`:**
- `technical` → prioritize "Code Examples", "Reference Tables", and "Commands & APIs" sections; preserve exact syntax
- `text` → All sections apply; map them to narrative content:

  | Template Field | Novel / Prose Mapping |
  |---|---|
  | **Core Idea** | 1–2 sentence summary of the chapter's narrative core |
  | **Frameworks Introduced** | New systems, techniques, factions, artifacts, or worldbuilding elements introduced |
  | **Key Concepts** | Characters appearing + new terms with definitions |
  | **Mental Models** | Character decision logic, survival strategies, combat formulas, recurring patterns in the narrative |
  | **Anti-patterns** | Mistakes, traps, or wrong choices characters make (or avoid) — what not to do |
  | **Key Takeaways** | Plot progression points, revelations, setup for future events |
  | **Connects To** | Cross-references to related chapters, setups, or payoffs |

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


### Generate chapters/index.md

After generating all chapter summary files, create `$OUTPUT_DIR/chapters/index.md` as a standalone chapter index. This replaces the inline chapter table that previously lived in `knowledge.md`, so the master file stays within its 4,000-token budget regardless of chapter count.

```markdown
# Chapter Index
> Auto-generated. Do not edit manually.

- Total: <N> chapters, <V> volumes
- Volume-level summaries: see each `vol-<NN>/README.md`

---

## Volume 1: <Title> (chapters <start>-<end>)

| # | Title | Frameworks | File |
|---|-------|------------|------|
| 0001 | <Title> | <framework1>, <framework2> | [vol-01/ch-0001-<slug>.md](vol-01/ch-0001-<slug>.md) |
| 0002 | <Title> | <framework1>, <framework2> | [vol-01/ch-0002-<slug>.md](vol-01/ch-0002-<slug>.md) |
| ... | ... | ... | ... |

---

## Volume 2: <Title> (chapters <start>-<end>)

| # | Title | Frameworks | File |
|---|-------|------------|------|
| 0101 | <Title> | <framework1>, <framework2> | [vol-02/ch-0101-<slug>.md](vol-02/ch-0101-<slug>.md) |
| ... | ... | ... | ... |
```

For books with no volume subdivision, place all chapters under a single section:

```markdown
## Body (chapters 1-<N>)

| # | Title | Frameworks | File |
|---|-------|------------|------|
| 0001 | <Title> | <framework1>, <framework2> | [ch-0001-<slug>.md](ch-0001-<slug>.md) |
```

The topic index (previously in `knowledge.md`) also moves here. Append after the volume listing:

```markdown
---

## Topic Index

- **<Term>** → ch-<NNNN>[, ch-<NNNN>]
```

Use the data collected during Step 7 (each chapter's title, frameworks, key terms, and file path) to populate the index. This file serves as the navigation entry point for book-knowledge queries.

**Topic Index minimum density**: At least 1 entry per 50 chapters. A 2,000-chapter
book must have ≥ 40 Topic Index entries. Cover all major characters, settings,
artifacts, and recurring concepts — not just the top 10. The Topic Index is how
book-knowledge queries find the right chapter; a sparse index defeats its purpose.

**Frameworks column is REQUIRED.** The column must list the key frameworks,
concepts, or events introduced or resolved in each chapter/batch. Do not omit it.
This is the primary search key for book-knowledge queries.

---

## Step 8 — Generate supporting files

### Directory structure

Create subdirectories for supporting files to support layered architecture (matching the `chapters/` pattern):

```bash
mkdir -p "$OUTPUT_DIR/glossary"
mkdir -p "$OUTPUT_DIR/patterns"
mkdir -p "$OUTPUT_DIR/cheatsheet"
```

### glossary

**Entry file** — `$OUTPUT_DIR/glossary.md`:
- Volume-level summary of high-frequency terms
- Format: per-volume sections with `**Term**: definition (Ch N, Ch M...)`
- Max 1,500 tokens (compaction truncates from end)
- Links to full index: `Full index in glossary/index.md`

**Full index** — `$OUTPUT_DIR/glossary/index.md`:
- Every significant term from the book, alphabetically sorted by first letter
- Format: `## A\n- **Term**: Ch N, Ch M...` (no definitions, just chapter references)
- No token limit (loaded on-demand)

**Per-volume files** — `$OUTPUT_DIR/glossary/vol-NN.md`:
- All terms introduced in volume NN
- Format: `**Term**: definition (1 sentence) — first appears in ch-NNNN`
- Generated during Step 7 chapter summary generation

### patterns

**Entry file** — `$OUTPUT_DIR/patterns.md`:
- Volume-level summary of core patterns
- Format: per-volume sections with pattern names and when-to-use
- Max 2,000 tokens (compaction truncates from end)
- Links to full index: `Full index in patterns/index.md`

**Full index** — `$OUTPUT_DIR/patterns/index.md`:
- All concrete techniques, design patterns from the book
- Format: `## Pattern Name\n**When to use**: ...\n**Chapters**: N, M...`
- No token limit (loaded on-demand)

**Per-volume files** — `$OUTPUT_DIR/patterns/vol-NN.md`:
- Detailed pattern analysis for volume NN
- Includes worked examples and trade-offs

### cheatsheet

**Entry file** — `$OUTPUT_DIR/cheatsheet.md`:

**This is the most differentiated layer of the knowledge base — treat it as a reasoning aid, not a keyword list.** Anyone can grep the glossary for a term. The cheatsheet captures the author's *judgment*: the decisions they'd make and why. It's the file that turns "I know the words" into "I'd act the way the author would".

- Volume-level summary of decision rules
- Max 1,200 tokens (compaction truncates from end)
- Links to full index: `Full index in cheatsheet/index.md`

**Full index** — `$OUTPUT_DIR/cheatsheet/index.md`:
- Complete decision rules, trade-off matrices, thresholds
- No token limit (loaded on-demand)

**Per-volume files** — `$OUTPUT_DIR/cheatsheet/vol-NN.md`:
- Detailed decision trees and flowcharts for volume NN

Prioritize, in order:
1. **Decision rules** — "When X, do Y, because Z." The if/then logic the author applies, stated so the reader can apply it without re-reading the book.
2. **Decision trees / flowcharts** (as nested bullets or a small table) — for choices with more than two branches.
3. **Trade-off matrices** — competing options scored on the dimensions the author cares about, so the reader can pick under their own constraints.
4. **Thresholds & defaults** — the specific numbers, ratios, or rules of thumb the author commits to (e.g. "keep functions under ~20 lines", "alert when error budget < 10%").
5. **Tells & smells** — fast heuristics for recognizing a situation ("if you see X, you're probably in trouble Y").

Avoid: bare term→definition rows (that's the glossary), and prose paragraphs (that's the chapters). Every line should help the reader *decide* something.

Format mostly as compact tables and decision rules; the content you'd want on a single printed page kept beside you while working.

### Step 8z — Completeness validation

**MANDATORY: Before leaving Step 8, verify that ALL of the following files exist
and have content (not just headers or stubs).**

For a single-volume book:
```
$OUTPUT_DIR/glossary.md              — entry file (≥ 500 tokens)
$OUTPUT_DIR/glossary/index.md        — full index (≥ 20 entries)
$OUTPUT_DIR/patterns.md              — entry file (≥ 500 tokens)
$OUTPUT_DIR/patterns/index.md        — full index (≥ 5 patterns)
$OUTPUT_DIR/cheatsheet.md            — entry file (≥ 300 tokens)
$OUTPUT_DIR/cheatsheet/index.md      — full index (≥ 5 decision rules)
```

For multi-volume books, additionally verify per-volume files:
```
$OUTPUT_DIR/glossary/vol-*.md        — at least one per volume with content
$OUTPUT_DIR/patterns/vol-*.md        — at least one per volume with content
$OUTPUT_DIR/cheatsheet/vol-*.md      — at least one per volume with content
```

If any required file is missing or is a stub (empty or just a heading), create it
with properly extracted content before proceeding to Step 9.

---

## Step 9 — Generate the master knowledge.md

**CRITICAL TOKEN BUDGET: Keep knowledge.md body under 4,000 tokens.**
Compaction truncates from the END — put the most important content FIRST.

Create `$OUTPUT_DIR/knowledge.md`:

```markdown
# <Full Title> — Knowledge Base
**Author**: <Author(s)> | **Chapters**: <N> | **Volumes**: <V> | **Generated**: <YYYY-MM-DD>

## Core Frameworks
<!-- ~2,000 tokens: the author's most important named frameworks and principles.
     Preserve exact names. Write as "Use X when Y", "Prefer X over Y because Z".
     This is a toolkit, not a summary. -->

<generate 2,000 tokens of the most critical frameworks and insights here>

---

## Chapter Index

<N> chapters across <V> volumes.
Full per-chapter index (frameworks, terms, file links) in [chapters/index.md](chapters/index.md).

| Volume | Chapters | Key Topics |
|--------|----------|------------|
| 1 | 1-100 | <topic1>, <topic2> |
| 2 | 101-250 | <topic3>, <topic4> |
| ... | ... | ... |

## Supporting Files

- [chapters/index.md](chapters/index.md) — Per-chapter index
- [glossary/index.md](glossary/index.md) — Glossary of terms (full index)
- [patterns/index.md](patterns/index.md) — Patterns & techniques (full index)
- [cheatsheet/index.md](cheatsheet/index.md) — Quick reference (full index)
```

Note: unlike agent skill SKILL.md files, knowledge.md uses plain markdown with no YAML frontmatter. This makes it directly readable by any tool, agent, or human without platform-specific parsing.

---

## Step 10 — Generate source metadata and rebuild index

### 10a — Generate source.yaml

Create `$OUTPUT_DIR/source.yaml` with the original source metadata:

```yaml
# knowledge/<slug>/source.yaml
knowledge_version: "1.2"
slug: "<slug>"
title: "<Full Title>"
author: "<Author(s)>"
source_format: "<epub|txt|pdf|...>"
word_count: <N>
chapter_count: <N>
generated_date: "<YYYY-MM-DD>"
tags: ["<tag1>", "<tag2>"]
content_type: "<text|technical>"
depth: "<volume|flat>"
volumes:
  - number: 1
    title: "<Volume Title>"
    chapter_start: <N>
    chapter_end: <N>
    source_file: "<filename>"
    import_date: "<YYYY-MM-DD>"
```

`depth` indicates whether the knowledge base has per-volume files in its auxiliary layers
(glossary/patterns/cheatsheet).  Set to `"volume"` when volume aggregation mode (Step 7a)
was used (chapters > 200).  Set to `"flat"` for single-volume books (≤ 200 chapters) where
only entry files and full indexes are generated.

`volumes` is optional — omit for single-volume books or when volume information is not available. When present, each entry records a volume's title, chapter range, source file, and import date to support batch imports and per-volume queries.

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
📄 Chapters: <N> | Volumes: <V>

Completeness Check:
  knowledge.md              — ✅ (~X tokens)
  source.yaml               — ✅
  chapters/index.md         — ✅ (entries: <N>, topic index: <M> entries)
  chapters/                 — ✅ (<N> summary files)
  glossary.md               — ✅ (~X tokens)
  glossary/index.md         — ✅ (<N> terms)
  glossary/vol-*.md         — ✅/⚠ (<N> files)
  patterns.md               — ✅ (~X tokens)
  patterns/index.md         — ✅ (<N> patterns)
  patterns/vol-*.md         — ✅/⚠ (<N> files)
  cheatsheet.md             — ✅ (~X tokens)
  cheatsheet/index.md       — ✅ (<N> rules)
  cheatsheet/vol-*.md       — ✅/⚠ (<N> files)
  ─────────────────
  All required layers: ✅

Usage:
  book-knowledge load <slug>                        → load core frameworks
  book-knowledge query <slug> <topic>               → find and explain a topic
  book-knowledge chapter <slug> <ch-NNNN>           → dive into a specific chapter
  grep "| <NNNN> |" chapters/index.md               → locate chapter file by number
  grep "<topic>" chapters/index.md                  → find chapters covering a topic
  grep "<term>" glossary/index.md                   → find term chapter references
  grep "<pattern>" patterns/index.md                → find pattern usage
```

---

## Update / Fold-in Workflow

When performing an Update/Fold-in operation on an existing knowledge base at `$OUTPUT_DIR/`:

### 1. Read Existing Structure
Read and parse the existing knowledge files:
- Read `$OUTPUT_DIR/knowledge.md` to parse the existing **Chapter Index**, **Topic Index**, metadata (author, total chapters), and **Core Frameworks**.
- Read `$OUTPUT_DIR/chapters/index.md` to find the existing chapter range (or scan `$OUTPUT_DIR/chapters/` if no index.md exists yet). The highest existing chapter number determines where new chapters start.
- Read `$OUTPUT_DIR/glossary.md`, `$OUTPUT_DIR/glossary/index.md` to see what terms are already indexed. Scan `$OUTPUT_DIR/glossary/vol-*.md` for per-volume term files.
- Read `$OUTPUT_DIR/patterns.md`, `$OUTPUT_DIR/patterns/index.md` to see what patterns are already indexed. Scan `$OUTPUT_DIR/patterns/vol-*.md` for per-volume pattern files.
- Read `$OUTPUT_DIR/cheatsheet.md`, `$OUTPUT_DIR/cheatsheet/index.md` to see what rules are already indexed. Scan `$OUTPUT_DIR/cheatsheet/vol-*.md` for per-volume cheatsheet files.

### 2. Match Content & Identify Revisions vs. Additions
Analyze the new extracted text in `<tempdir>/book_skill_work/full_text.txt` to identify if the new content represents:
- **Updates/Revisions to existing chapters**: If a section of the new content directly updates or expands an existing chapter's topic, read the existing chapter file, merge the new details into it, and rewrite the file.
- **New additions**: If the content introduces new chapters, papers, or separate sections, create **new chapter summary files** under `chapters/` (or the appropriate `chapters/vol-<VV>/` subdirectory). Start numbering these files after the highest existing chapter number (e.g. if the existing chapters stop at `ch-0012`, create `ch-0013-*.md`, `ch-0014-*.md`, etc.). If a `--chapter-range` was provided, use the declared range instead of auto-numbering.

### 3. Generate or Update Chapter Summary Files
For each new or revised chapter:
- Read the corresponding section of the extracted new text.
- Follow the formatting guidelines in **Step 7** to build the summary.
- Write/update the file in `$OUTPUT_DIR/chapters/` (or the appropriate `vol-<VV>/` subdirectory).

After all new/revised chapters are written, **regenerate `$OUTPUT_DIR/chapters/index.md`** to reflect the updated chapter list, incorporating any new entries and merging the topic index. Follow the same format described in Step 7's "Generate chapters/index.md" section.

### 4. Merge Supporting Files

#### Glossary merge
- **Read existing structure**:
  - Read `$OUTPUT_DIR/glossary.md` (entry file with volume summary)
  - Read `$OUTPUT_DIR/glossary/index.md` (full index)
  - Scan `$OUTPUT_DIR/glossary/vol-*.md` for existing per-volume files
- **Extract new terms**: From new content, extract all terms following Step 8 glossary guidelines
- **Write per-volume files**: Create or update `$OUTPUT_DIR/glossary/vol-NN.md` for each affected volume
- **Update full index**: Merge new terms into `$OUTPUT_DIR/glossary/index.md`, alphabetically sorted
- **Update entry file**: Regenerate `$OUTPUT_DIR/glossary.md` with updated volume summary (keep under 1,500 tokens)

#### Patterns merge
- **Read existing structure**:
  - Read `$OUTPUT_DIR/patterns.md` (entry file with volume summary)
  - Read `$OUTPUT_DIR/patterns/index.md` (full index)
  - Scan `$OUTPUT_DIR/patterns/vol-*.md` for existing per-volume files
- **Extract new patterns**: From new content, extract techniques, algorithms, patterns
- **Write per-volume files**: Create or update `$OUTPUT_DIR/patterns/vol-NN.md` with detailed analysis
- **Update full index**: Merge new patterns into `$OUTPUT_DIR/patterns/index.md`
- **Update entry file**: Regenerate `$OUTPUT_DIR/patterns.md` with updated volume summary (keep under 2,000 tokens)

#### Cheatsheet merge
- **Read existing structure**:
  - Read `$OUTPUT_DIR/cheatsheet.md` (entry file with volume summary)
  - Read `$OUTPUT_DIR/cheatsheet/index.md` (full index)
  - Scan `$OUTPUT_DIR/cheatsheet/vol-*.md` for existing per-volume files
- **Extract new rules**: From new content, extract decision rules, trade-off matrices, thresholds
- **Write per-volume files**: Create or update `$OUTPUT_DIR/cheatsheet/vol-NN.md` with detailed decision trees
- **Update full index**: Merge new rules into `$OUTPUT_DIR/cheatsheet/index.md`
- **Update entry file**: Regenerate `$OUTPUT_DIR/cheatsheet.md` with updated volume summary (keep under 1,200 tokens)

### 5. Re-generate the Master knowledge.md
Update the master knowledge file `$OUTPUT_DIR/knowledge.md`:
- **Metadata**: Increment the chapter count, update the volume list, and add the new source names if appropriate. Update the `Generated` date to the current date.
- **Core Frameworks**: Fold in the most high-impact mental models or principles from the new content (ensuring the overall file remains under 4,000 tokens).
- **Chapter Index (per-volume summary)**: Update the per-volume summary table (volume / chapter range / key topics). The per-chapter detail is already handled by the regenerated `chapters/index.md` and does not belong here.
- **Auxiliary Files**: Ensure the link to `chapters/index.md` is present.

### 6. Completeness validation (Update)
Run the same completeness checklist defined in **Step 8z** against the updated output
directory.  Verify that merged per-volume pattern files, per-volume cheatsheet files,
and per-chapter glossary files all exist after the merge.  If any merged layer is
missing content (e.g. a `patterns/vol-01.md` that was updated but has no new entries),
go back and fill it before proceeding.

### 7. Proceed to Step 10
Once the files are successfully written, merged, and validated, skip to **Step 10** to
generate source.yaml, rebuild the index, cleanup, and print an update report summarizing
the newly added chapters, merged glossary terms, and updated indices.

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
9. **Topic index minimum density** — at least 1 Topic Index entry per 50 chapters. A 2,000-chapter book needs ≥ 40 entries. Cover characters, settings, artifacts, techniques, and recurring concepts — not just the first 10 that come to mind.
10. **Completeness before proceeding** — never leave Step 8 without verifying that all four auxiliary layers (glossary, patterns, cheatsheet) have both entry files and per-volume/per-chapter depth files with real content. Run the checklist in Step 8z before moving on.
