"""Markdown documentation parser for TetherDust MCP server.

Parses markdown files to extract:
- Table schemas (columns, types, descriptions)
- Documentation content for search
- Query examples

Supports:
- Multiple documentation sources (each top-level folder = a source)
- Django integration (reads DocumentationSource from database when available)
- Auto-discovery from TETHERDUST_DOCUMENTATIONS_DIR for standalone MCP usage
- Hot-reload: documentation is re-parsed when the cache expires
  based on a configurable interval (TETHERDUST_HOT_RELOAD_INTERVAL env var)
"""

import os
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DocumentationSourceConfig:
    """Configuration for a documentation source (maps to a folder)."""

    name: str
    path: str
    description: str = ""
    file_patterns: list[str] = field(default_factory=lambda: ["*.md"])


@dataclass
class TableColumn:
    """Represents a column in a database table."""

    name: str
    data_type: str
    description: str = ""
    nullable: bool = True
    enum_values: list[str] = field(default_factory=list)


@dataclass
class TableSchema:
    """Represents a documented database table."""

    name: str
    domain: str = ""
    description: str = ""
    columns: list[TableColumn] = field(default_factory=list)
    source_file: str = ""
    source_name: str = ""


@dataclass
class QueryExample:
    """Represents a documented SQL query example."""

    title: str
    description: str
    sql: str
    tables: list[str] = field(default_factory=list)
    use_cases: list[str] = field(default_factory=list)
    source_file: str = ""
    source_name: str = ""


@dataclass
class SearchResult:
    """Represents a documentation search result."""

    content: str
    source_file: str
    relevance_score: float = 0.0
    heading: str = ""
    source_name: str = ""


def _load_sources_from_django() -> list[DocumentationSourceConfig] | None:
    """Try to load documentation sources from Django database.

    Returns None if Django is not available or not configured.
    """
    django_settings = os.environ.get("DJANGO_SETTINGS_MODULE")
    if not django_settings:
        return None

    try:
        import django

        django.setup()
        from engine.models import DocumentationSource

        sources = DocumentationSource.objects.filter(is_active=True).order_by("folder_name")
        return [
            DocumentationSourceConfig(
                name=src.folder_name,
                path=src.resolved_path,
                description=src.description,
                file_patterns=src.file_patterns if src.file_patterns else ["*.md"],
            )
            for src in sources
        ]
    except Exception:
        return None


def _load_sources_from_env() -> list[DocumentationSourceConfig]:
    """Auto-discover documentation sources from TETHERDUST_DOCUMENTATIONS_DIR.

    Scans the directory for top-level folders, each becoming a source.
    Falls back to DOCS_PATH for legacy single-path setups.
    """
    import logging

    _logger = logging.getLogger(__name__)

    # Auto-discover from documentations directory
    docs_dir = os.environ.get("TETHERDUST_DOCUMENTATIONS_DIR", "").strip()
    if docs_dir:
        docs_path = Path(docs_dir)
        if docs_path.exists() and docs_path.is_dir():
            sources = []
            for entry in sorted(docs_path.iterdir()):
                if entry.is_dir() and not entry.name.startswith("."):
                    sources.append(
                        DocumentationSourceConfig(
                            name=entry.name,
                            path=str(entry),
                        )
                    )
            if sources:
                _logger.info(
                    "Auto-discovered %d doc sources from %s: %s",
                    len(sources),
                    docs_dir,
                    [s.name for s in sources],
                )
                return sources

    return []


class DocumentationParser:
    """Parses markdown documentation files from multiple sources."""

    def __init__(
        self,
        docs_path: str | None = None,
        sources: list[DocumentationSourceConfig] | None = None,
    ):
        """Initialize parser.

        Args:
            docs_path: Legacy single-path mode. Creates a default source.
            sources: List of documentation source configurations. Takes
                precedence over docs_path. If neither is provided, sources
                are loaded from Django DB or environment variables.
        """
        self._sources: list[DocumentationSourceConfig] = []

        if sources is not None:
            self._sources = sorted(sources, key=lambda s: s.name)
        elif docs_path is not None:
            self._sources = [DocumentationSourceConfig(name="default", path=docs_path)]
        # else: sources loaded lazily in _ensure_loaded

        self._table_cache: dict[str, TableSchema] = {}
        self._examples_cache: list[QueryExample] = []
        self._loaded = False
        self._loaded_at: float = 0.0
        self._hot_reload_interval: int | None = None

    def _get_hot_reload_interval(self) -> int:
        """Get hot-reload interval in seconds from environment."""
        if self._hot_reload_interval is None:
            try:
                self._hot_reload_interval = int(os.getenv("TETHERDUST_HOT_RELOAD_INTERVAL", "0"))
            except ValueError:
                self._hot_reload_interval = 0
        return self._hot_reload_interval

    def _ensure_loaded(self) -> None:
        """Lazy load documentation if not already loaded, or reload if cache expired."""
        interval = self._get_hot_reload_interval()
        if self._loaded and interval > 0:
            elapsed = time.monotonic() - self._loaded_at
            if elapsed >= interval:
                self._loaded = False

        if not self._loaded:
            self._load_all()
            self._loaded = True
            self._loaded_at = time.monotonic()

    def _resolve_sources(self) -> list[DocumentationSourceConfig]:
        """Resolve documentation sources, loading from Django or env if needed."""
        if self._sources:
            return self._sources

        import logging

        _logger = logging.getLogger(__name__)

        # Try Django first, then auto-discover from filesystem
        django_sources = _load_sources_from_django()
        if django_sources is not None:
            self._sources = django_sources
            _logger.info("Using Django doc sources: %d", len(self._sources))
        else:
            self._sources = _load_sources_from_env()
            _logger.info("Using env doc sources: %d", len(self._sources))

        return self._sources

    @staticmethod
    def _is_under(path: Path, root: Path) -> bool:
        """Check if *path* is inside *root* (both must be resolved)."""
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def _iter_files(self, source: DocumentationSourceConfig) -> Iterator[tuple[Path, str]]:
        """Iterate over matching files in a documentation source.

        Yields (file_path, relative_display_path) tuples.

        Only files whose resolved path is inside the source's own root are
        yielded; any path that would escape via symlinks or ``..`` is silently
        skipped.
        """
        root = Path(source.path).expanduser()
        if not root.exists() or not root.is_dir():
            return

        resolved_root = root.resolve()

        patterns = source.file_patterns if source.file_patterns else ["*.md"]
        for pattern in patterns:
            for file_path in root.rglob(pattern):
                if not file_path.is_file():
                    continue
                # Resolve symlinks before the containment check so that a
                # symlink pointing outside the source root is caught.
                resolved = file_path.resolve()
                if not self._is_under(resolved, resolved_root):
                    continue
                rel = str(file_path.relative_to(root))
                display = f"{source.name}/{rel}" if source.name != "default" else rel
                yield file_path, display

    def _load_all(self) -> None:
        """Load all documentation from disk across all sources."""
        self._table_cache.clear()
        self._examples_cache.clear()

        sources = self._resolve_sources()

        seen_files: set[str] = set()

        for source in sources:
            for file_path, display_path in self._iter_files(source):
                # Deduplicate by absolute path
                abs_path = str(file_path.resolve())
                if abs_path in seen_files:
                    continue
                seen_files.add(abs_path)

                content = file_path.read_text(encoding="utf-8")

                # Parse table schemas
                for table in self._parse_table_schemas(content, display_path, source):
                    table.source_name = source.name
                    self._table_cache[table.name.lower()] = table

                # Parse query examples
                for example in self._parse_query_examples(content, display_path):
                    example.source_name = source.name
                    self._examples_cache.append(example)

    def _parse_table_schemas(
        self,
        content: str,
        source_file: str,
        source: DocumentationSourceConfig | None = None,
    ) -> Iterator[TableSchema]:
        """Extract table schema definitions from markdown content.

        Supports the per-file table format where each file documents one table:
        - Table name derived from the filename (e.g., CardInquiry.md -> CardInquiry)
        - Description from the first paragraph after ``# Overview``
        - Columns from ``## ColumnName type`` headings under ``# Columns``
        """
        # Derive table name from filename
        file_stem = Path(source_file).stem
        # Skip non-table docs (e.g., Architecture.md)
        if not re.match(r"^[A-Z]", file_stem) or file_stem.lower() in ("architecture", "readme"):
            return

        # Check that this looks like a table doc (has a # Columns section)
        if not re.search(r"^#\s+Columns\s*$", content, re.MULTILINE):
            return

        # Extract description from # Overview section
        overview_match = re.search(
            r"^#\s+Overview\s*\n+(.*?)(?=^#\s|\Z)",
            content,
            re.MULTILINE | re.DOTALL,
        )
        description = overview_match.group(1).strip() if overview_match else ""

        # Extract columns from ## headings under # Columns
        columns_match = re.search(
            r"^#\s+Columns\s*\n(.*?)(?=^#\s[^#]|\Z)",
            content,
            re.MULTILINE | re.DOTALL,
        )
        columns: list[TableColumn] = []
        if columns_match:
            columns = list(self._parse_heading_columns(columns_match.group(1)))

        domain = self._extract_domain(source_file, source)

        yield TableSchema(
            name=file_stem,
            domain=domain,
            description=description,
            columns=columns,
            source_file=source_file,
        )

    def _parse_heading_columns(self, columns_section: str) -> Iterator[TableColumn]:
        """Parse columns from ``## ColumnName type`` heading format.

        Expected format per column:
            ## ColumnName type ?
            Description text.
            Known values / Examples / etc.
        """
        # Split on ## headings, capturing the heading line
        parts = re.split(r"^##\s+(.+)$", columns_section, flags=re.MULTILINE)
        # parts = ['before', 'heading1', 'body1', 'heading2', 'body2', ...]

        for i in range(1, len(parts), 2):
            heading = parts[i].strip()
            body = parts[i + 1].strip() if i + 1 < len(parts) else ""

            # Parse heading: "ColumnName type ?" where ? means nullable
            tokens = heading.split()
            name = tokens[0]
            nullable = heading.endswith("?")

            # Type is everything after the name, minus trailing ?
            type_str = " ".join(tokens[1:]).rstrip("? ").strip() if len(tokens) > 1 else ""

            # First line of body is the description
            body_lines = body.split("\n")
            description = body_lines[0].strip() if body_lines else ""

            # Extract known/enum values
            enum_values: list[str] = []
            enum_match = re.search(r"Known values.*?:\n((?:- .+\n?)+)", body, re.IGNORECASE)
            if enum_match:
                enum_values = [
                    line.lstrip("- ").split(":")[0].strip()
                    for line in enum_match.group(1).strip().split("\n")
                    if line.strip().startswith("-")
                ]

            yield TableColumn(
                name=name,
                data_type=type_str,
                description=description,
                nullable=nullable,
                enum_values=enum_values,
            )

    def _parse_query_examples(self, content: str, source_file: str) -> Iterator[QueryExample]:
        """Extract SQL query examples from markdown content.

        Expects format:
        ### Query Title
        Description of what the query does.

        **Use cases:** order lookup, reporting

        **Tables:** Order, Customer

        ```sql
        SELECT * FROM Order WHERE ...
        ```
        """
        example_pattern = re.compile(
            r"^###\s+(.+?)\s*\n"  # Title
            r"(.*?)"  # Description and metadata
            r"```sql\s*\n(.*?)```",  # SQL code block
            re.MULTILINE | re.DOTALL,
        )

        for match in example_pattern.finditer(content):
            title = match.group(1).strip()
            metadata = match.group(2)
            sql = match.group(3).strip()

            # Extract description (first paragraph)
            desc_match = re.match(r"([^\n*]+)", metadata.strip())
            description = desc_match.group(1).strip() if desc_match else ""

            # Extract use cases
            use_cases: list[str] = []
            use_case_match = re.search(r"\*\*Use cases?:\*\*\s*([^\n]+)", metadata, re.IGNORECASE)
            if use_case_match:
                use_cases = [uc.strip() for uc in use_case_match.group(1).split(",")]

            # Extract tables
            tables: list[str] = []
            tables_match = re.search(r"\*\*Tables?:\*\*\s*([^\n]+)", metadata, re.IGNORECASE)
            if tables_match:
                tables = [t.strip() for t in tables_match.group(1).split(",")]

            yield QueryExample(
                title=title,
                description=description,
                sql=sql,
                tables=tables,
                use_cases=use_cases,
                source_file=source_file,
            )

    def _extract_domain(
        self,
        file_path: str,
        source: DocumentationSourceConfig | None = None,
    ) -> str:
        """Extract domain from source name or file path.

        If the source has a meaningful name (not 'default'), use it as domain.
        Otherwise fall back to the first directory in the file path.
        """
        if source and source.name != "default":
            # Use source name as domain (e.g., "Orders Tables" -> "Orders Tables")
            return source.name

        # Fall back to directory-based domain
        parts = Path(file_path).parts
        if len(parts) > 1:
            return parts[0].title()
        return ""

    def list_tables(self) -> list[TableSchema]:
        """Return all documented tables."""
        self._ensure_loaded()
        return list(self._table_cache.values())

    def get_table_schema(self, table_name: str) -> TableSchema | None:
        """Get schema for a specific table."""
        self._ensure_loaded()
        return self._table_cache.get(table_name.lower())

    def get_query_examples(
        self, table_name: str | None = None, use_case: str | None = None
    ) -> list[QueryExample]:
        """Get query examples, optionally filtered by table or use case."""
        self._ensure_loaded()

        results = self._examples_cache

        if table_name:
            table_lower = table_name.lower()
            results = [ex for ex in results if any(t.lower() == table_lower for t in ex.tables)]

        if use_case:
            use_case_lower = use_case.lower()
            results = [
                ex
                for ex in results
                if any(use_case_lower in uc.lower() for uc in ex.use_cases)
                or use_case_lower in ex.description.lower()
                or use_case_lower in ex.title.lower()
            ]

        return results

    def search_docs(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Search documentation content for relevant sections.

        Searches across all configured documentation sources.
        Uses simple keyword matching. For better results, consider
        implementing embeddings-based search in a future phase.
        """
        self._ensure_loaded()

        results: list[SearchResult] = []
        query_terms = query.lower().split()
        sources = self._resolve_sources()
        seen_files: set[str] = set()

        for source in sources:
            for file_path, display_path in self._iter_files(source):
                abs_path = str(file_path.resolve())
                if abs_path in seen_files:
                    continue
                seen_files.add(abs_path)

                content = file_path.read_text(encoding="utf-8")

                # Build searchable context from file name (without extension)
                file_stem = file_path.stem.lower()

                # Split into sections by headings
                sections = re.split(r"(^#{1,3}\s+.+$)", content, flags=re.MULTILINE)

                current_heading = ""
                for section in sections:
                    if re.match(r"^#{1,3}\s+", section):
                        current_heading = section.strip("# \n")
                        continue

                    # Score against section body + heading + file name combined
                    searchable = (f"{current_heading}\n{section}\n{file_stem}").lower()
                    score = sum(1 for term in query_terms if term in searchable)

                    if score > 0:
                        snippet = self._extract_snippet(section, query_terms)
                        results.append(
                            SearchResult(
                                content=snippet,
                                source_file=display_path,
                                relevance_score=score / len(query_terms),
                                heading=current_heading,
                                source_name=source.name,
                            )
                        )

        # Sort by relevance and return top results
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results[:max_results]

    def _extract_snippet(
        self, content: str, query_terms: list[str], context_chars: int = 300
    ) -> str:
        """Extract a relevant snippet from content around query terms."""
        content_lower = content.lower()

        # Find first occurrence of any query term
        first_pos = len(content)
        for term in query_terms:
            pos = content_lower.find(term)
            if pos != -1 and pos < first_pos:
                first_pos = pos

        if first_pos == len(content):
            first_pos = 0

        # Extract context around the match
        start = max(0, first_pos - context_chars // 2)
        end = min(len(content), first_pos + context_chars // 2)

        snippet = content[start:end].strip()

        # Add ellipsis if truncated
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."

        return snippet

    def reload(self) -> None:
        """Force reload of all documentation."""
        self._table_cache.clear()
        self._examples_cache.clear()
        self._loaded = False
        self._ensure_loaded()
