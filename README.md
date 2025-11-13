# CiteShield - Legal Citation Verification CLI

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**CiteShield** is an AI-powered command-line tool that reviews legal briefs and memos to verify citation accuracy. Using the [`openai-agents-python`](https://github.com/openai/openai-agents-python) SDK, it extracts every cited authority, checks whether the cited proposition is accurate, and flags hallucinated or weak citations before filing.

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Usage](#usage)
  - [Basic Usage](#basic-usage)
  - [Advanced Options](#advanced-options)
  - [Output Formats](#output-formats)
- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [Capabilities](#capabilities)
- [Extending CiteShield](#extending-citeshield)
- [API Usage](#api-usage)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

## Features

- **Automated Citation Extraction**: Identifies all legal citations (cases, statutes, regulations, secondary sources)
- **AI-Powered Verification**: Uses OpenAI agents to verify each citation supports its claimed proposition
- **Web Search Integration**: Optional web search to confirm citations exist and are accurately represented
- **Multiple File Formats**: Supports .txt, .md, .pdf, and .docx files
- **Flexible Input**: Paste text directly from the terminal or load existing documents
- **Structured Output**: Returns detailed reports in table or JSON format
- **Risk Assessment**: Flags citations as verified, needs review, not found, or contradicted
- **Line-Level References**: Pinpoints exact locations in source documents
- **Configurable Models**: Works with various OpenAI models (gpt-4.1-mini, o4-mini, etc.)
- **Extensible Architecture**: Easy to add custom tools or integrate with legal databases

## Quick Start

```bash
# 1. Create a virtual environment
python3 -m venv .venv && source .venv/bin/activate

# 2. Install the package
pip install -e .

# 3. Set your OpenAI API key
export OPENAI_API_KEY=sk-your-api-key-here

# 4. Run verification on a sample brief
citation-agent verify ./samples/brief.txt
```

That's it! CiteShield will analyze the document and display a comprehensive citation report.

## Installation

### Requirements

- Python 3.10 or higher
- OpenAI API key ([Get one here](https://platform.openai.com/api-keys))

### Standard Installation

```bash
# Clone the repository
git clone https://github.com/Themis-Legal-Framework/-CiteShield-legal-citation-verifier-CLI.git
cd -CiteShield-legal-citation-verifier-CLI

# Install the package
pip install -e .
```

### With Optional Dependencies

For PDF support:
```bash
pip install -e ".[pdf]"
```

For Word document support:
```bash
pip install -e ".[docx]"
```

For all optional dependencies:
```bash
pip install -e ".[pdf,docx]"
```

## Usage

### Basic Usage

```bash
# Verify a text file
citation-agent verify brief.txt

# Verify a PDF
citation-agent verify motion.pdf

# Verify a Word document
citation-agent verify memo.docx

# Paste text directly (press Ctrl-D when finished on macOS/Linux)
citation-agent verify -

# Provide inline text without creating a file
citation-agent verify --text "Roe v. Wade ..."
```

### Advanced Options

```bash
# Use a specific OpenAI model
citation-agent verify brief.txt --model gpt-4.1

# Disable web search for faster processing
citation-agent verify brief.txt --no-web-search

# Increase reasoning turns for complex documents
citation-agent verify brief.txt --max-turns 12

# Adjust temperature for more deterministic results
citation-agent verify brief.txt --temperature 0.0

# Combine multiple options
citation-agent verify brief.txt --model o4-mini --max-turns 15 --temperature 0.2
```

### Output Formats

**Table Format (Default)**
```bash
citation-agent verify brief.txt
```
Displays a beautifully formatted table with citation analysis in your terminal.

**JSON Format**
```bash
citation-agent verify brief.txt --output json
```
Outputs machine-readable JSON for integration with other tools or workflows.

**Saving Output to File**
```bash
citation-agent verify brief.txt --output json > report.json
```

### Getting Help

```bash
# View all available options
citation-agent verify --help

# See information about agent tools
citation-agent explain-tools
```

## How It Works

1. The file is normalized to text (with optional extras for `.pdf` and `.docx`).
2. The document is chunked and line-numbered so the agent can cite exact passages through custom tools:
   - `list_brief_sections` (paginate through chunks),
   - `get_brief_section` (return verbatim text with line numbers),
   - `search_brief_sections` (keyword lookup).
3. The agent (`CiteShield`) receives the entire numbered document plus access to the tools above. When enabled, it also gets the hosted `web_search` tool from OpenAI so it can confirm that each case or statute exists and supports the quoted rule.
4. The agent must return a strict [`CitationVerificationReport`](src/citation_agent/models.py) describing totals, risk, and a per-citation breakdown (status, reasoning, suggested fixes).

Because it is powered by OpenAI's Responses API underneath, the agent can call the base LLM multiple times, invoke the hosted web search tool, or reach any additional Model Context Protocol tools you wire up later (for example, connections to Westlaw, Lexis, or an internal know-how database).

## Architecture

CiteShield is built with a modular architecture:

```
src/citation_agent/
├── __init__.py          # Package exports
├── models.py            # Pydantic models for structured output
├── document.py          # Document loading and chunking utilities
├── tools.py             # Custom agent tools for document navigation
├── service.py           # Main orchestration service
└── cli.py               # Command-line interface
```

**Key Components:**

- **Models**: Pydantic schemas ensure structured, validated output from the AI agent
- **Document Processing**: Handles multiple file formats and chunks large documents efficiently
- **Custom Tools**: Provides the agent with document navigation capabilities (list, get, search)
- **Service Layer**: Orchestrates the entire verification workflow
- **CLI**: User-friendly command-line interface with rich formatting

For more details, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Capabilities

### LLM Reasoning
All auditing flows through configurable OpenAI models using the agents SDK. You can choose between:
- **Fast models** (`gpt-4.1-mini`) for quick, cost-effective verification
- **Reasoning models** (`o4-mini`, `o4`) for complex legal analysis
- Mix and match based on your needs

### Document Navigation Tools
Custom tools keep prompts efficient and enable precise citation:
- **`list_brief_sections`**: Browse document structure with pagination
- **`get_brief_section`**: Retrieve full text of specific sections
- **`search_brief_sections`**: Find sections by keyword

These tools minimize token usage while maintaining accuracy.

### Hosted Web Search
Enable with `--web-search` (enabled by default). Uses OpenAI's built-in search tool to:
- Confirm citations exist
- Verify quoted text matches the source
- Check that citations support claimed propositions
- Detect hallucinated or misattributed citations

### Structured Output
All results conform to the `CitationVerificationReport` schema, providing:
- **Total Statistics**: Overall document assessment
- **Individual Analysis**: Detailed breakdown per citation
- **Risk Levels**: Low, medium, high classifications
- **Recommendations**: Suggested fixes for problematic citations
- **Supporting Evidence**: URLs, quotes, and reasoning

### Future Extensions
The SDK natively supports:
- **Model Context Protocol (MCP) servers** for legal databases
- **Vector search tools** for better citation recall
- **Code interpreter** for analyzing complex legal documents
- **File search tools** for cross-referencing multiple documents

## Extending CiteShield

### Adding Custom Tools

Create custom tools to extend the agent's capabilities:

```python
from agents import function_tool

@function_tool
def check_westlaw(citation: str) -> str:
    """Check if citation exists in Westlaw."""
    # Your implementation here
    return "Citation found in Westlaw"

# Add to agent in service.py
tools = [list_brief_sections, get_brief_section, search_brief_sections, check_westlaw]
```

### Integrating MCP Servers

Connect to legal databases via Model Context Protocol:

```python
from agents.mcp import MCPServer

# In service.py, _build_agent method
mcp_server = MCPServer("legal-db-server", config={...})
agent = Agent(
    name="cite-shield",
    tools=tools,
    mcp_servers=[mcp_server],
    ...
)
```

### Automation Workflows

Build CI/CD pipelines around CiteShield:

```bash
# Example: Block filing if citations fail
citation-agent verify brief.pdf --output json > report.json
if jq -e '.overall_assessment != "pass"' report.json; then
    echo "Citations need review before filing!"
    exit 1
fi
```

### Custom Chunking Strategies

Modify document chunking for your needs:

```python
# In document.py
def chunk_document(text: str, *, max_lines: int = 80, overlap: int = 10):
    # Adjust parameters for larger/smaller chunks
    ...
```

## API Usage

CiteShield can also be used as a Python library:

```python
from pathlib import Path
from citation_agent import CitationAgentService, AgentConfig

# Configure the service
config = AgentConfig(
    model="gpt-4.1-mini",
    temperature=0.1,
    max_turns=8,
    enable_web_search=True
)

# Create service and run verification
service = CitationAgentService(config=config)
report = service.run(Path("brief.txt"))

# Access results
print(f"Overall Assessment: {report.overall_assessment}")
print(f"Total Citations: {report.total_citations}")
print(f"Verified: {report.verified_citations}")
print(f"Flagged: {report.flagged_citations}")

# Iterate through individual citations
for citation in report.citations:
    print(f"{citation.citation_text}: {citation.verification_status}")
    if citation.recommended_fix:
        print(f"  Fix: {citation.recommended_fix}")
```

## Troubleshooting

| Problem | Solution |
| --- | --- |
| `OPENAI_API_KEY` missing | Export the key: `export OPENAI_API_KEY=sk-...` or add to `.env` file |
| PDF import error | Install PDF support: `pip install citation-agent[pdf]` |
| Word document error | Install docx support: `pip install citation-agent[docx]` |
| `MaxTurnsExceeded` | Increase `--max-turns 12` or split large documents into smaller files |
| Slow performance | Disable web search with `--no-web-search` for faster processing |
| Inaccurate results | Try a more powerful model: `--model gpt-4.1` or `--model o4-mini` |
| Rate limit errors | Add retry logic or reduce concurrency in your workflow |
| Memory issues with large PDFs | Convert to text first or split into multiple files |

### Getting Support

- **Issues**: Report bugs or request features on [GitHub Issues](https://github.com/Themis-Legal-Framework/-CiteShield-legal-citation-verifier-CLI/issues)
- **Discussions**: Ask questions in [GitHub Discussions](https://github.com/Themis-Legal-Framework/-CiteShield-legal-citation-verifier-CLI/discussions)
- **Documentation**: See [ARCHITECTURE.md](ARCHITECTURE.md) for technical details

## Development

### Setting Up Development Environment

```bash
# Clone the repository
git clone https://github.com/Themis-Legal-Framework/-CiteShield-legal-citation-verifier-CLI.git
cd -CiteShield-legal-citation-verifier-CLI

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install in development mode with all extras
pip install -e ".[pdf,docx]"

# Install development dependencies
pip install pytest pytest-cov black ruff mypy
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=citation_agent --cov-report=html

# Run specific test file
pytest tests/test_service.py
```

### Code Quality

```bash
# Format code with Black
black src/ tests/

# Lint with Ruff
ruff check src/ tests/

# Type checking with mypy
mypy src/
```

## Contributing

Contributions are welcome! Please follow these guidelines:

1. **Fork the repository** and create a feature branch
2. **Write tests** for new functionality
3. **Follow code style**: Use Black for formatting, Ruff for linting
4. **Add documentation**: Update README and docstrings
5. **Submit a pull request** with a clear description of changes

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [OpenAI Agents SDK](https://github.com/openai/openai-agents-python)
- Uses [Typer](https://typer.tiangolo.com/) for CLI
- Terminal output powered by [Rich](https://rich.readthedocs.io/)
- Data validation with [Pydantic](https://docs.pydantic.dev/)

---

**Note**: CiteShield is a tool to assist in citation verification. It should be used as part of a comprehensive legal review process, not as a replacement for professional legal judgment.
