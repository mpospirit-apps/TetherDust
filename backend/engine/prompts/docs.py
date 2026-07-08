"""Prompts for AI documentation generation (single-file and multi-file library).

Call sites: ``management/views/docsource.py``. The static template text lives here;
the per-run save instructions (destination, databases, codebases) are appended by
the caller, since they depend on request context.
"""

WIKILINK_NOTE = (
    "\n\nWhen referencing other documentation pages, use wiki-link syntax: "
    "[[Source/path.md|Display Text]]. The docs viewer renders these as clickable links."
)

# Environment context shared by single-file and library generation. Tells the
# agent what tools it has, how its output is rendered, and how to save — none of
# which is inferable from a generic "how to document" template. Prepended to the
# task template by both builders below.
TETHERDUST_CONTEXT = """\
## Working inside TetherDust

You are not editing files in a local checkout. You explore databases and codebases
through MCP tools and write finished markdown through one tool. These principles hold
throughout: ground every claim in source, name real code entities, show structure
visually, and cross-link rather than repeat.

Your read tools — explore before you write:

| Tool | Use it to |
| --- | --- |
| `list_databases`, `list_tables` | Discover databases and their documented tables |
| `get_table_schema` | Read a table's columns, types, enums, existing notes |
| `query_database` | Run read-only SELECTs to confirm real values, distributions, enum members |
| `get_query_examples` | Pull existing example queries for a table |
| `search_docs` | Search already-written documentation (flows, relationships, concepts) |
| `list_codebases` | Discover the source repositories available to you |
| `get_codebase_tree(codebase, path)` | Map a repo's directory structure to roles |
| `read_codebase_file(codebase, path)` | Read actual source to ground behavioral claims |
| `search_codebase(codebase, query)` | Locate a function, symbol, or pattern across a repo |

Work in this order: map directories to roles first (`get_codebase_tree`); trace one
representative flow end to end (`read_codebase_file` / `search_codebase`); confirm the
data model (`get_table_schema` / `query_database`); then document subsystem by subsystem.

Citing source in TetherDust: there is no git history or commit hash here, so do not
invent line ranges or pin to commits. Cite what you actually read — codebase claims as
the codebase name and file path (e.g. `engine/agents/base.py`) naming the real
function/class; data-model claims as `database -> table -> column`. Never assert a
behavior you did not retrieve with a read tool; if a tool could not return it, omit it.

Rendering — write for the viewer (Python-Markdown with fenced code, GFM tables, TOC,
syntax highlighting, plus mermaid and wiki-links):
- Tables: use GFM pipe tables for any enumerable set.
- Diagrams: use ```mermaid fenced blocks (flowcharts, ER, sequence) — rendered as SVG by
  mermaid.js, themed to the UI. Use them for every flow and hierarchy.
- Cross-links: use wiki-link syntax [[Folder/Page.md|Display Text]] — document each topic
  once and link everywhere else that touches it. Linking to a sibling page at the library
  root can use a bare filename ([[Page.md|Display Text]], no slash). Any link that contains
  a slash is read as Folder/path, so a page in a subfolder, or in another library, needs the
  full source-prefixed path ([[Library Name/Schemas/Page.md|Display Text]]).
- Non-markdown files (.sql, .py) render as highlighted code, not as markdown.

Saving — `create_documentation` is the only way to write; never emit documentation as a
chat response. Parameters: `destination` (folder under sources/docs/, subfolders
allowed, created if absent), `filename` (.md appended automatically), `content` (your full
markdown), `databases` (optional — names to introspect; appends a Database Schema
Reference with the table/column dump, so use it on schema pages instead of hand-copying
columns), and `reference_docs` (optional — existing doc-source names; appends Related
Documentation as wiki-links). The written file is immediately searchable via search_docs.
"""

# The five disciplines that separate documentation an engineer trusts from
# documentation they don't. Shared by single-file and library generation.
CORE_PRINCIPLES = """\
# Core principles

These five rules govern all documentation you produce.

Ground every claim in source. Each factual statement maps to a specific file (and the
symbol within it) or a specific database/table/column you actually read with a tool.
Never describe behavior you have not located. When a behavior cannot be traced to a
source location, omit it rather than guess. Documentation that cites
`engine/agents/base.py` and `BaseAgent.chat` builds trust; documentation that asserts
"the agent is fast" does not.

Name real code entities. Use the actual class, function, struct, and file names from the
codebase, not invented or paraphrased ones — the symbols an engineer will grep for.
Conceptual descriptions that do not connect to greppable identifiers are not actionable.

Layer from concrete to detailed. Start with what the thing is and why it exists, then how
it is organized, then how a request or data item flows through it, then component depth. A
reader should be able to stop at any layer and have a coherent understanding for that level.

Show structure visually. Tables for anything enumerable (file roles, config options, API
symbols, lifecycle stages). Diagrams for anything with flow or hierarchy (request
lifecycles, dependency trees, layer architecture). Prose only for the connective reasoning.

Cross-link, don't repeat. Each topic is documented in exactly one place. Everywhere else
that touches it links to that place. This keeps pages focused and prevents the
contradictions that appear when the same thing is explained twice.
"""


DOC_TEMPLATES = {
    "database_table": (
        "Generate markdown documentation for the following database tables. "
        "For each table, create a section with:\n"
        "- An **Overview** describing the table's purpose\n"
        "- A **Columns** section describing each column with its type and meaning\n"
        "- **Known enum values** where applicable\n\n"
        "Output the documentation as a single markdown document with H1 for each table."
        + WIKILINK_NOTE
    ),
    "architecture": (
        "Generate architecture documentation describing how these database tables "
        "and systems relate to each other. Include:\n"
        "- Entity relationships\n"
        "- Data flow between tables\n"
        "- Domain concepts and business logic\n\n"
        "Output as a single markdown document." + WIKILINK_NOTE
    ),
    "query_examples": (
        "Generate useful SQL query examples for the following database tables. "
        "For each example, include:\n"
        "- A descriptive title\n"
        "- A brief description of what the query does and when to use it\n"
        "- The list of tables used\n"
        "- The SQL query in a code block\n\n"
        "Output as a single markdown document." + WIKILINK_NOTE
    ),
}


def build_doc_generation_prompt(doc_type: str, context_parts: list[str], scope: str = "") -> str:
    """Build the full prompt for AI documentation generation."""
    system = DOC_TEMPLATES.get(doc_type, DOC_TEMPLATES["database_table"])
    parts = [CORE_PRINCIPLES, "\n---\n", TETHERDUST_CONTEXT, "\n---\n", system]
    if scope.strip():
        parts.append(f"\n\nScope and goals:\n{scope.strip()}")
    if context_parts:
        parts.append("\n---\n\nSource material:\n")
        parts.extend(context_parts)
    return "\n".join(parts)


# The multi-page playbook: how to shape an overview + deep-dive library and the
# order to build it in. Library-only — single-file generation produces one page,
# so this scaffolding would be noise there.
LIBRARY_GUIDE = """\
# Building a documentation library

A library works at two levels: a single Overview page that orients, and many deep-dive
pages that each cover one subsystem. The overview answers "what is this and how is it
shaped"; the deep-dives answer "how does this specific part work." Wire them together with
explicit links in both directions — the overview points down into subsystems, each
subsystem points back up and sideways to related ones.

## The page hierarchy

A typical top-level structure (adapt it to the system's actual shape — not every codebase
needs every section):

| Section | Purpose |
| --- | --- |
| Overview | What the system is, design philosophy, high-level architecture, repo map |
| Getting Started | Dependencies, setup, minimal working example |
| Core Architecture | The central abstractions and how they interact |
| Subsystem deep-dives | One page per major functional area |
| Configuration | How behavior is controlled at build and run time |
| APIs and Integration | Public surface; how external code calls in |
| Development and Testing | Build system, test framework, CI/CD |
| Deployment / Release | How it ships and is versioned |
| Glossary | Domain terms defined in one place |

You are not limited to a flat list of files: `create_documentation`'s `destination` may
include subfolders (e.g. `Subsystems/Auth`), which are created automatically. Group related
pages into directories once a section has more than a handful of pages — keep a small
library flat, but reach for folders (`Schemas/`, `Subsystems/`, `API/`) as it grows.

## The Overview page (index.md)

The most-read page. Orient a newcomer in minutes while staying accurate enough that an
expert does not wince. Build it from these components, in roughly this order:

- Purpose and scope — two or three sentences on what the system does and who it is for,
  immediately followed by links to the deep-dive pages so readers can jump.
- What it is — plain-language explanation of the job it does and the problem it solves;
  name foundational dependencies and the primary entry point (the root class, the
  `main()`, the struct everything hangs off).
- Design philosophy — the two or three principles that explain the codebase's shape, the
  "why" behind decisions a reader would otherwise find arbitrary.
- Key features — a table: feature, description, and where useful an impact column.
- High-level architecture — a mermaid diagram mapping subsystem names to the concrete code
  entities that implement them, then a short prose walkthrough. Every box is a real,
  nameable thing in the repo.
- The primary flow — trace one representative path end to end as a numbered sequence (a
  request lifecycle, a data flow, a call pipeline). This single trace teaches more than any
  amount of component description because it shows the components cooperating.
- Repository structure — a table mapping top-level directories to their roles.
- Core dependencies and versions — pulled from the actual manifest (`package.json`,
  `pyproject.toml`, `Cargo.toml`, `CMakeLists.txt`) and cited.

## Deep-dive subsystem pages

Each major subsystem gets its own page with a consistent internal shape — once a reader
learns the rhythm of one page, every other page is navigable:

- Purpose and scope — what the subsystem does, in terms of the abstractions it owns, then
  links to adjacent subsystems ("for how this integrates with X, see [[X]]").
- Core architecture / data model — the central data structure or class: name it, cite its
  definition, table its important members.
- Mechanism sections — one section per distinct mechanism (declaration, resolution,
  caching, error handling). Each: name the function/class that implements it, describe what
  it does, and where behavior branches show the branches as a table or decision tree.
- Flow diagrams — where the subsystem has a sequence or tree, diagram it in mermaid.
- Performance characteristics — where it matters, a table of operations with their cost and
  when they run.
- Summary table of key components — close with a table: component, file location, primary
  responsibility. This is the page's index for a returning reader.

## A repeatable process

Work in this order; each step produces an artifact the next builds on:

1. Read the manifest and entry point first (via the codebase read tools). Together they
   tell you what the system is and where execution begins.
2. Map the top-level directories to roles — produce the repository-structure table before
   anything else; each major directory tends to become a deep-dive page.
3. State the purpose and philosophy. If you cannot articulate the philosophy yet, keep
   reading — do not invent one.
4. Trace one primary flow end to end, noting every function and file it touches. This
   reveals which subsystems are central versus peripheral.
5. Identify the two-to-five engine abstractions everything revolves around; these anchor the
   architecture diagram and each get prominent treatment.
6. Document subsystems one at a time, applying the deep-dive page shape, citing as you go —
   never write a behavioral claim you have not located in source.
7. Cross-link and add the glossary. Verify the overview links down to every subsystem and
   each subsystem links back; define domain terms once.

## What to avoid

Do not write claims you cannot cite. Do not paraphrase code entity names; use the exact
greppable identifiers. Do not explain the same mechanism in two places; document once and
link. Do not bury enumerable facts in prose when a table would let readers scan. Do not let
the overview drown in detail that belongs in a deep-dive, and do not let a deep-dive omit
the high-level framing that situates it. Do not cite files or symbols you did not actually
open with the read tools.

## Checklist

Before considering the library done, confirm:

- index.md states what the system is, why it exists, and its design philosophy
- Repository structure mapped directory-to-role in a table
- Core dependencies and version pulled from the manifest and cited
- High-level architecture diagram maps concepts to real code entities
- One primary flow traced end to end as a numbered sequence
- Each major subsystem has its own page with a consistent internal shape
- Every subsystem page names its engine data structure and tables its members
- Each mechanism ties to a specific function/class you read
- Enumerable facts are in tables; flows and hierarchies are in mermaid diagrams
- Every section carries a source citation (codebase file/symbol, or database -> table ->
  column)
- Cross-links connect the overview to subsystems and subsystems to neighbors
- Domain terms defined once in a glossary
"""


# Database libraries follow a fixed, table-oriented shape instead of the free-form
# subsystem playbook above: one Architecture.md overview plus one Tables/<TableName>.md
# per table. The library root the user named is the package root — there is no extra
# wrapper folder. General purpose: no business-domain or tech-stack assumptions.
DATABASE_LIBRARY_GUIDE = """\
# Database documentation guide

This guide defines the conventions for documenting a database. Follow it for the library
you were asked to build. The goal is a reference an engineer trusts: every table findable,
every column explained, every claim grounded in something you actually read with a tool.

The library root you were given is the package root — everything lives directly under it,
with no extra wrapper folder.

## Directory structure

```
<LibraryRoot>/
├── Architecture.md
└── Tables/
    ├── <TableName>.md
    └── ...
```

- `Architecture.md` — overview, layer diagram (with a codebase), and ER diagram index
- `Tables/<TableName>.md` — one file per table: full column docs (and data flows with a codebase)

Save `Architecture.md` with destination `<LibraryRoot>` and each table page with
destination `<LibraryRoot>/Tables`. The filename is the exact table name.

## Explore before you write

Ground the data model in real introspection, not assumptions:

- `list_tables` / `get_table_schema` — the authoritative column list, types, nullability,
  keys, and any enum/check constraints. Never hand-guess a type or nullability.
- `query_database` — read-only SELECTs to confirm real example values, enum members in use,
  null ratios, and row-count scale. This is how `Examples:` and `### Concerns` get real data.
- `get_query_examples` / `search_docs` — reuse query patterns and prose already written.

Start `Architecture.md` only after you have walked every table once; write each table page
from its own schema read.

## What to document depends on your sources

Some sections below describe application behavior, not just the data model. Only write them
when a codebase source is attached to this run:

- Code-grounded (require a codebase): Technology Stack, Layers, Data Flows, Key Files Involved.
- Schema-grounded (always): Overview, the Tables ER diagrams, Columns, Example Queries.

If no codebase is attached, omit the code-grounded sections entirely rather than guessing —
document the data model from schema introspection alone.

## How your pages render

The viewer is Python-Markdown (`fenced_code`, `tables`, `toc`, `codehilite`) plus mermaid.js
and wiki-links. Write to these capabilities — they are what make a page navigable:

- `[TOC]` — place it on its own line directly under the H1 of `Architecture.md` and of any
  table page with many columns. Every `##`/`###` heading becomes a clickable anchor, so the
  per-column headings in `# Columns` turn into a jump list for free.
- Mermaid — fence `erDiagram`, `sequenceDiagram`, and `flowchart LR` blocks; they render as
  SVG themed to the UI. Never hand-draw a schema or a flow in ASCII when a diagram will do.
- GFM tables — use pipe tables for any enumerable set (table-group summaries, technology
  stack, performance notes). Rows are scannable in a way prose is not.
- Wiki-links — `[[<LibraryRoot>/Tables/TableName.md|TableName]]` links between pages. Link
  `Architecture.md` down to every table page, and each table page back up to `Architecture.md`
  and across to the tables it references by foreign key. Use the full root-prefixed path.
- Highlighted SQL — every ` ```sql ` block is colorized by Pygments, so write real, runnable
  SQL in Example Queries rather than pseudo-code.

---

## Architecture.md

Open with the H1, then `[TOC]`. Required sections, in order:

#### 1. `# Overview`

One or two short paragraphs on the database's purpose: what subject area it owns, what
writes to it, what reads from it, and the scale (rough row counts / how many tables). Close
with wiki-links into the table pages so a reader can jump straight to a table of interest.

#### 2. `## Technology Stack` (codebase required)

A bullet list with bold labels. Only include lines that apply, and name the real framework /
engine you found in the codebase — do not list a stack you did not verify:

```markdown
- **Framework**: the application framework, if any
- **Architecture Pattern**: Layered / Service-oriented / Modular / …
- **Database**: the engine and its access layer (ORM or driver)
- **Messaging**: message bus or queue, if any
- **Scheduling**: background-job scheduler, if any
- **Additional**: caching, logging, mapping, and other notable libraries
```

#### 3. `# Layers` (codebase required)

A Mermaid `flowchart LR` showing every major component and how data flows between them. Use
`subgraph` blocks for grouping (Clients, API Layer, Services, Background Jobs, Database
Tables, External). Label edges with the operation type where meaningful.

```mermaid
flowchart LR
  subgraph clients["Clients"]
    client["Client"]
  end
  subgraph api["API Layer"]
    ctrl["Controller"]
  end
  subgraph db["Database Tables"]
    tbl["SomeTable"]
  end
  client -->|request| ctrl
  ctrl -->|writes| tbl
```

Follow the diagram with a prose description of each layer. Use `---` separators between
layers and `###` for named components within a layer.

#### 4. `# Tables`

One or more Mermaid `erDiagram` blocks. List each table's key columns inside the entity and
draw relationships with crow's-foot cardinality (`||--o{` one-to-many, `||--||` one-to-one,
`}o--o{` many-to-many). Split a large schema into several diagrams grouped by relationship
rather than one unreadable graph.

```mermaid
erDiagram
    PARENT ||--o{ CHILD : has
    PARENT {
        bigint Id PK
        nvarchar Name
    }
    CHILD {
        bigint Id PK
        bigint ParentId FK
        int Status
    }
```

After the diagrams, give a grouped summary. A GFM table reads better than prose here:

```markdown
## Group Name

| Table | Stores |
|---|---|
| TableA | What it stores |
| TableB | What it stores |
```

Use `---` to separate groups, and wiki-link each table name to its page.

---

## Tables/\\<TableName\\>.md

Open with the H1, then `[TOC]` when the column list is long. Required sections, in order:

#### 1. `# Overview`

Two to four sentences: what entity the table represents, what writes to it, what reads from
it, and its key relationships. Wiki-link related tables (`[[<LibraryRoot>/Tables/Other.md|Other]]`)
and link back up to `Architecture.md`.

#### 2. `# Data Flows` (codebase required)

One `##` section per meaningful flow that touches this table — cover every INSERT, UPDATE,
and significant SELECT pattern. Each flow section, in this order:

```markdown
## <Flow Name>

**Purpose:** One sentence — what this flow achieves.

**When to use:** One sentence — what triggers this flow.

**Key Steps:**
- Step 1
- Step 2

```mermaid
sequenceDiagram
    participant A as Caller
    participant B as Service
    participant DB as Database<br/>TableName

    Note over A,DB: <Flow Name>
    A->>B: Action
    B->>DB: INSERT / UPDATE / SELECT TableName
    DB-->>B: Result
    B-->>A: Response
```

**Key Files Involved:**
- path/to/file (FunctionOrMethodName)

**Database Changes:**
- TableName: What changes (new row inserted / column X updated / read-only)
```

Separate flows with `---`.

#### 3. `# Columns`

One `##` subsection per column, in schema order. The `##` headings feed the page's `[TOC]`,
so a reader can jump straight to a column:

```markdown
## ColumnName datatype ?

Description — what this field means, how it is used, any non-obvious constraints.

Known values (EnumName):
- value1: Label
- value2: Label

Examples: `val1`, `val2`, `val3`
```

Rules:
- Append `?` after the datatype for nullable columns.
- Prefix the primary key column name with `🔑` (e.g. `## 🔑 Id bigint`).
- Mark foreign keys and wiki-link the referenced table page.
- Include a `Known values` block for any column that maps to an enum or a fixed set of codes.
- Provide real example values pulled with `query_database` — `Examples:` (comma-separated)
  or `Example:`. Mask anything sensitive.
- If a column has data-quality concerns, add a `### Concerns` subsection with figures you
  confirmed by query:

```markdown
### Concerns

- Missing row count: 86
- Missing row ratio: 0.02%
```

#### 4. `# Example Queries`

One or more labelled SQL blocks for the table's most common query patterns. Each renders
syntax-highlighted, so write real SQL. Use `@Param` notation for parameters and a leading
comment when the intent is not obvious:

```markdown
## Query Label

```sql
-- What this query answers
SELECT
    Col1,
    Col2
FROM Schema.TableName
WHERE SomeId = @SomeId
ORDER BY CreatedDateUtc DESC;
```
```

---

## Style rules

| Rule | Detail |
|---|---|
| Page open | H1, then `[TOC]` on long pages |
| Heading depth | `#` Overview → `##` Section → `###` Subsection |
| Mermaid | `flowchart LR` for architecture, `erDiagram` for schema, `sequenceDiagram` for flows |
| Cross-links | Wiki-link pages with the full root-prefixed path |
| Nullability | Mark nullable columns with `?` after the type |
| Enums | Document known values inline in the column section |
| Examples | Use real values pulled with a read tool (masked if sensitive) |
| Separators | Use `---` between major items within a section |
| File names | Match the exact database table name, no spaces — `<TableName>.md` |
| SQL style | Qualify tables with schema where relevant (`Schema.Table`); use `@Param` for params |

---

## Checklist

- [ ] `Architecture.md` has Overview and ER diagrams (plus Tech Stack and Layers with a codebase)
- [ ] One `Tables/<TableName>.md` per table, written from its own schema read
- [ ] Every table file has Overview, Columns, and an Example Query (Data Flows too with a codebase)
- [ ] `[TOC]` sits under the H1 on Architecture.md and on long table pages
- [ ] Primary key column marked with `🔑`; nullable columns marked with `?`; foreign keys linked
- [ ] All enum/status columns have `Known values` documented
- [ ] Example values and Concerns figures come from real `query_database` reads
- [ ] ER diagrams show FK relationships with crow's-foot notation (`||--o{`)
- [ ] Sequence diagrams use `Note over A,B:` to label the flow name
- [ ] Architecture.md links down to every table page and each table page links back
"""


def build_library_prompt(library_name: str, doc_type: str = "codebase") -> str:
    """Build the base prompt for an AI-planned multi-file documentation library.

    ``doc_type`` selects the guide: ``"database"`` uses the fixed table-oriented
    DATABASE_LIBRARY_GUIDE (Architecture.md + Tables/<TableName>.md); anything else
    uses the free-form subsystem LIBRARY_GUIDE. The agent designs the file structure
    and writes every file via repeated create_documentation calls; per-file
    destinations and the save instructions are appended by the caller.
    """
    if doc_type == "database":
        guide = DATABASE_LIBRARY_GUIDE
        task = (
            f'Your task: document the database as a library named "{library_name}" — an '
            "Architecture.md overview plus one Tables/<TableName>.md page per table, "
            "following the structure and conventions above."
        )
    else:
        guide = LIBRARY_GUIDE
        task = (
            f'Your task: build a documentation library named "{library_name}" — a tree of '
            "related markdown files (with subfolders) that together document the selected "
            "sources comprehensively, following the structure and process above."
        )

    parts = [
        CORE_PRINCIPLES,
        "\n---\n",
        TETHERDUST_CONTEXT,
        "\n---\n",
        guide,
        "\n---\n",
        task,
    ]

    return "\n".join(parts)
