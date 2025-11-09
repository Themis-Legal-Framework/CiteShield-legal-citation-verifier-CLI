# CiteShield Architecture

This document provides a comprehensive overview of the CiteShield citation verification system's architecture, design patterns, and implementation details.

## Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Module Breakdown](#module-breakdown)
- [Data Flow](#data-flow)
- [Agent Design](#agent-design)
- [Custom Tools System](#custom-tools-system)
- [Document Processing Pipeline](#document-processing-pipeline)
- [Output Schema](#output-schema)
- [Extension Points](#extension-points)
- [Performance Considerations](#performance-considerations)
- [Security Considerations](#security-considerations)

## Overview

CiteShield is a legal citation verification tool built on the OpenAI Agents SDK. It uses AI agents with custom tools to navigate and analyze legal documents, verifying that citations accurately support their claimed propositions.

### Core Technologies

- **Python 3.10+**: Modern Python with type hints
- **OpenAI Agents SDK**: Agentic workflow orchestration
- **Pydantic**: Data validation and structured outputs
- **Typer**: CLI framework
- **Rich**: Terminal UI rendering

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      CLI Interface (cli.py)                  │
│  - Command parsing (Typer)                                   │
│  - Output formatting (Rich)                                  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Service Layer (service.py)                      │
│  - Workflow orchestration                                    │
│  - Agent configuration                                       │
│  - Result extraction                                         │
└────────────┬───────────────────────────────┬────────────────┘
             │                               │
             ▼                               ▼
┌────────────────────────┐      ┌───────────────────────────┐
│  Document Processor    │      │    OpenAI Agent           │
│  (document.py)         │      │    (Agents SDK)           │
│  - File loading        │      │  - LLM reasoning          │
│  - Chunking            │      │  - Tool calling           │
│  - Line numbering      │      │  - Web search             │
└────────────┬───────────┘      └────────┬──────────────────┘
             │                           │
             │                           ▼
             │                  ┌────────────────────────────┐
             └─────────────────▶│  Custom Tools (tools.py)   │
                                │  - list_brief_sections     │
                                │  - get_brief_section       │
                                │  - search_brief_sections   │
                                └────────────────────────────┘
                                          │
                                          ▼
                                ┌──────────────────────────┐
                                │  BriefContext            │
                                │  - Document chunks       │
                                │  - Metadata              │
                                └──────────────────────────┘
```

## Module Breakdown

### 1. models.py - Data Models

**Purpose**: Define structured schemas for agent inputs and outputs using Pydantic.

**Key Classes:**

```python
CitationAssessment
├── citation_text: str           # The exact citation from document
├── citation_type: CitationType  # case, statute, regulation, etc.
├── proposition_summary: str     # What the citation claims to support
├── verification_status: str     # verified, needs_review, not_found, contradicted
├── reasoning: str               # AI's explanation
├── supporting_authorities: list # Evidence (URLs, quotes)
├── risk_level: RiskLevel        # low, medium, high
└── recommended_fix: str?        # Optional suggestion

CitationVerificationReport
├── document_name: str
├── overall_assessment: str      # pass, needs_review, high_risk
├── total_citations: int
├── verified_citations: int
├── flagged_citations: int
├── unable_to_locate: int
├── narrative_summary: str
└── citations: list[CitationAssessment]
```

**Design Decisions:**
- Pydantic ensures type safety and automatic validation
- Structured output forces the agent to provide consistent results
- Enums (via Literal types) constrain agent responses to valid values
- Optional fields allow flexibility while maintaining structure

### 2. document.py - Document Processing

**Purpose**: Handle document ingestion, preprocessing, and chunking for efficient agent processing.

**Key Classes & Functions:**

```python
DocumentChunk
├── index: int           # Chunk sequence number
├── start_line: int      # First line (1-indexed)
├── end_line: int        # Last line (1-indexed)
├── text: str            # Content with line numbers
└── preview: str         # Short preview for listings

Functions:
- load_document_text()   # Multi-format file loading
- chunk_document()       # Split into overlapping chunks
- annotate_document()    # Add line numbers
- summarize_chunks()     # Generate overview
```

**Chunking Strategy:**
- Default: 40 lines per chunk with 5-line overlap
- Overlap ensures citations spanning chunk boundaries aren't missed
- Line numbers preserved for precise citation references
- Configurable chunk size for different document types

**Supported Formats:**
- Text files (.txt, .md)
- PDF documents (requires pypdf)
- Word documents (requires python-docx)

### 3. tools.py - Agent Tools

**Purpose**: Provide custom tools that allow the agent to navigate documents efficiently.

**Architecture:**

```python
BriefContext (State Container)
├── document_name: str
├── chunks: list[DocumentChunk]
└── overview: str

Tool Functions:
├── list_brief_sections()    # Browse with pagination
├── get_brief_section()      # Retrieve full section
└── search_brief_sections()  # Keyword search
```

**Tool Design Principles:**
1. **Minimize Token Usage**: Return only requested sections
2. **Structured Access**: Index-based and search-based retrieval
3. **Context Preservation**: Line numbers allow precise references
4. **Stateless**: Tools read from immutable BriefContext

**Search Algorithm:**
```python
def _score_chunk(chunk, query):
    score = (
        keyword_frequency +      # How many times keywords appear
        keyword_coverage +       # How many unique keywords found
        keyword_density          # Frequency relative to chunk size
    )
    return score
```

### 4. service.py - Orchestration Layer

**Purpose**: Coordinate the entire verification workflow from input to output.

**Key Classes:**

```python
AgentConfig
├── model: str = "gpt-4.1-mini"
├── temperature: float = 0.1
├── max_turns: int = 8
└── enable_web_search: bool = True

CitationAgentService
├── __init__(config)
├── run(brief_path) → CitationVerificationReport
├── _build_agent() → Agent
└── _build_agent_input() → str
```

**Workflow:**

1. **Document Loading**: Load and preprocess the file
2. **Chunking**: Split into navigable sections
3. **Agent Setup**: Configure tools and instructions
4. **Execution**: Run agent with context and tools
5. **Result Extraction**: Parse structured output

**Agent Instructions:**
- Dynamic instructions incorporate document metadata
- Emphasize thoroughness and accuracy
- Require structured output format
- Encourage use of web search for verification

### 5. cli.py - Command-Line Interface

**Purpose**: Provide user-friendly CLI with beautiful terminal output.

**Commands:**

```python
verify(file, model, temperature, max_turns, web_search, output)
├── Parse arguments
├── Configure service
├── Run verification
└── Format output (table or JSON)

explain_tools()
└── Display tool documentation
```

**Output Formats:**
- **Table**: Rich-formatted terminal output with colors and panels
- **JSON**: Machine-readable for automation and integration

## Data Flow

### Verification Pipeline

```
1. User Input
   └─▶ citation-agent verify brief.txt --model gpt-4.1-mini

2. CLI Processing (cli.py)
   └─▶ Parse arguments → Create AgentConfig

3. Service Initialization (service.py)
   └─▶ CitationAgentService(config)

4. Document Loading (document.py)
   ├─▶ load_document_text(brief.txt)
   ├─▶ chunk_document(text, max_lines=40, overlap=5)
   ├─▶ annotate_document(text)  # Add line numbers
   └─▶ summarize_chunks(chunks)

5. Agent Setup (service.py)
   ├─▶ Create BriefContext(chunks, metadata)
   ├─▶ Build agent with tools and instructions
   └─▶ Prepare initial prompt

6. Agent Execution (OpenAI Agents SDK)
   ├─▶ Agent receives prompt and tools
   ├─▶ Multiple reasoning iterations:
   │   ├─▶ Call list_brief_sections() to browse
   │   ├─▶ Call get_brief_section(N) to read
   │   ├─▶ Call search_brief_sections("citation")
   │   └─▶ Call web_search() to verify
   └─▶ Return CitationVerificationReport

7. Output Formatting (cli.py)
   ├─▶ Table format: Rich rendering
   └─▶ JSON format: Pydantic serialization

8. User Sees Result
   └─▶ Formatted report with citation analysis
```

### Tool Invocation Flow

```
Agent decides to use tool
    ↓
OpenAI Agents SDK calls tool function
    ↓
Tool receives RunContextWrapper[BriefContext]
    ↓
Tool accesses chunks from context
    ↓
Tool performs operation (list/get/search)
    ↓
Tool returns formatted string
    ↓
Agent receives result and continues reasoning
```

## Agent Design

### Agent Configuration

```python
Agent(
    name="cite-shield",
    instructions=dynamic_instructions_fn,
    tools=[
        list_brief_sections,
        get_brief_section,
        search_brief_sections,
        WebSearchTool()  # Optional
    ],
    model="gpt-4.1-mini",
    model_settings=ModelSettings(temperature=0.1),
    output_type=CitationVerificationReport
)
```

### Instruction Design

The agent receives context-aware instructions that:
- Identify it as "CiteShield", an exacting legal citation auditor
- Explain the document structure (name, chunk count)
- List available tools and their purposes
- Define the verification task precisely
- Require structured output
- Emphasize accuracy over speed
- Encourage thoroughness and web verification

### Reasoning Loop

```
Turn 1: Agent lists sections to understand document structure
Turn 2: Agent searches for first citation
Turn 3: Agent retrieves section containing citation
Turn 4: Agent uses web search to verify citation
Turn 5: Agent continues with next citation
...
Turn N: Agent returns CitationVerificationReport
```

**Max Turns**: Default 8, configurable via `--max-turns`
- Prevents infinite loops
- Can be increased for complex documents
- Each turn is one agent action (tool call or response)

## Custom Tools System

### Tool Registration

Tools are registered using the `@function_tool` decorator:

```python
from agents import function_tool, RunContextWrapper

@function_tool
def my_tool_impl(ctx: RunContextWrapper[BriefContext], param: str) -> str:
    """Tool description for the agent."""
    # Access context
    chunks = ctx.context.chunks
    # Perform operation
    result = do_something(chunks, param)
    return result

# Export wrapped tool
my_tool = function_tool(my_tool_impl)
```

### Context Management

**BriefContext** maintains state across tool calls:
- Immutable during agent execution
- Shared among all tools
- Passed via `RunContextWrapper`

**Benefits:**
- No global state
- Thread-safe design
- Clear data dependencies

### Tool Best Practices

1. **Return Strings**: Tools should return formatted text for agent consumption
2. **Handle Errors**: Validate inputs and return helpful error messages
3. **Document Well**: Docstrings become tool descriptions for the agent
4. **Keep Stateless**: Don't modify context, only read from it
5. **Format Output**: Return structured, easy-to-parse text

## Document Processing Pipeline

### Loading Strategy

```python
def load_document_text(path: Path) -> str:
    if suffix in {".txt", ".md", ""}:
        return path.read_text(encoding="utf-8")

    elif suffix == ".pdf":
        reader = PdfReader(path)
        return "\n".join(page.extract_text() for page in reader.pages)

    elif suffix == ".docx":
        document = docx.Document(path)
        return "\n".join(paragraph.text for paragraph in document.paragraphs)

    else:
        raise ValueError(f"Unsupported format: {suffix}")
```

### Chunking Algorithm

```python
def chunk_document(text, max_lines=40, overlap=5):
    lines = text.split("\n")
    chunks = []
    start = 0

    while start < len(lines):
        end = min(len(lines), start + max_lines)

        # Create chunk with line numbers
        numbered_lines = [
            f"{line_no:04d}: {line}"
            for line_no, line in enumerate(lines[start:end], start=start+1)
        ]

        chunks.append(DocumentChunk(
            index=len(chunks),
            start_line=start + 1,
            end_line=end,
            text="\n".join(numbered_lines)
        ))

        if end == len(lines):
            break

        # Overlap for continuity
        start = end - overlap

    return chunks
```

**Why Overlapping Chunks?**
- Citations can span multiple lines
- Legal concepts may be split across chunk boundaries
- Overlap ensures context is preserved
- Default 5-line overlap balances context vs. redundancy

## Output Schema

### Structured Output Enforcement

Pydantic models ensure the agent returns valid, structured data:

```python
# Agent must return this exact structure
report = CitationVerificationReport(
    document_name="brief.txt",
    overall_assessment="needs_review",
    total_citations=5,
    verified_citations=3,
    flagged_citations=2,
    unable_to_locate=0,
    narrative_summary="Found 5 citations, 2 require review...",
    citations=[
        CitationAssessment(
            citation_text="Brown v. Board, 347 U.S. 483",
            citation_type="case",
            proposition_summary="Separate is inherently unequal",
            verification_status="verified",
            reasoning="Web search confirmed...",
            supporting_authorities=["https://..."],
            risk_level="low",
            recommended_fix=None
        ),
        # ... more citations
    ]
)
```

**Validation:**
- Type checking at runtime
- Required fields enforced
- Enum values validated
- Automatic error messages if structure is wrong

### JSON Serialization

```python
# Convert to JSON
json_output = report.model_dump_json(indent=2)

# Parse back
report = CitationVerificationReport.model_validate_json(json_output)
```

## Extension Points

### 1. Adding New Document Formats

```python
# In document.py
def load_document_text(path: Path) -> str:
    ...
    elif suffix == ".rtf":
        # Add RTF support
        return extract_rtf_text(path)
```

### 2. Custom Tool Development

```python
# Create new tool
from agents import function_tool

@function_tool
def check_shepards(ctx: RunContextWrapper[BriefContext], citation: str) -> str:
    """Check citation status in Shepard's."""
    # Implementation
    return "Good law"

# Add to agent in service.py
tools = [...existing_tools..., check_shepards]
```

### 3. MCP Server Integration

```python
from agents.mcp import MCPServer

mcp_server = MCPServer(
    "westlaw-connector",
    config={"api_key": os.getenv("WESTLAW_KEY")}
)

agent = Agent(
    ...
    mcp_servers=[mcp_server]
)
```

### 4. Custom Verification Logic

```python
# Extend CitationAssessment
class EnhancedCitationAssessment(CitationAssessment):
    shepards_status: str | None = None
    bluebook_format_check: bool = False

# Update agent output_type
agent = Agent(..., output_type=EnhancedVerificationReport)
```

### 5. Post-Processing Hooks

```python
class CitationAgentService:
    def run(self, brief_path: Path) -> CitationVerificationReport:
        report = ... # existing logic

        # Add post-processing
        report = self._enrich_with_metadata(report)
        report = self._apply_custom_rules(report)

        return report
```

## Performance Considerations

### Token Usage Optimization

1. **Chunked Access**: Agent retrieves only needed sections
2. **Summarized Overview**: Chunks summarized to reduce initial tokens
3. **Incremental Loading**: Full text sent once, then referenced by line numbers
4. **Search Before Read**: Agent searches first, then retrieves only relevant chunks

### Processing Time

Factors affecting speed:
- **Document Length**: Longer documents = more citations = more turns
- **Model Choice**: gpt-4.1-mini is faster than o4
- **Web Search**: Adds latency (typically 2-5s per search)
- **Max Turns**: More turns = longer processing

**Optimization Strategies:**
```bash
# Fast mode (disable web search)
citation-agent verify brief.txt --no-web-search

# Use faster model
citation-agent verify brief.txt --model gpt-4.1-mini

# Reduce max turns for simple documents
citation-agent verify brief.txt --max-turns 5
```

### Scalability

**Single Document:**
- Handles documents up to ~50 pages efficiently
- Larger documents should be split

**Batch Processing:**
```python
# Process multiple documents
for file in Path("briefs/").glob("*.txt"):
    report = service.run(file)
    save_report(report, file.stem + "_report.json")
```

**Parallel Processing:**
```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=3) as executor:
    futures = [executor.submit(service.run, f) for f in files]
    reports = [f.result() for f in futures]
```

## Security Considerations

### Input Validation

1. **File Path Validation**: Only allow expected file extensions
2. **File Size Limits**: Prevent processing extremely large files
3. **Content Sanitization**: Clean input before sending to LLM

```python
def load_document_text(path: Path, max_size_mb: int = 10) -> str:
    if path.stat().st_size > max_size_mb * 1024 * 1024:
        raise ValueError(f"File too large: {path}")

    if path.suffix not in {".txt", ".md", ".pdf", ".docx"}:
        raise ValueError(f"Unsupported format: {path.suffix}")

    # Load and return
```

### API Key Management

```python
# Never hardcode keys
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY not set")

# Use environment variables or secret managers
# Consider using .env files with python-dotenv
```

### Output Sanitization

```python
# Be cautious with outputs that may contain sensitive data
# Consider redacting before logging
def safe_log(report: CitationVerificationReport):
    # Don't log full document content
    logger.info(f"Processed {report.document_name}: {report.overall_assessment}")
```

### Rate Limiting

```python
# Implement rate limiting for API calls
from tenacity import retry, wait_exponential, stop_after_attempt

@retry(wait=wait_exponential(min=1, max=60), stop=stop_after_attempt(3))
def run_with_retry(self, brief_path: Path):
    return self.run(brief_path)
```

---

## Summary

CiteShield's architecture prioritizes:
- **Modularity**: Clear separation of concerns
- **Extensibility**: Easy to add new features
- **Type Safety**: Pydantic models ensure correctness
- **Efficiency**: Chunking and tools minimize token usage
- **User Experience**: Rich CLI output and JSON export

The system is designed to be both powerful out-of-the-box and easy to customize for specific legal workflows.
