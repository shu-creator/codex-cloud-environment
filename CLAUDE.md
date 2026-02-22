# Project Overview
This project is a document auto-generation harness for Claude Code.
It enables autonomous creation of PowerPoint (.pptx) and Word (.docx) documents
via Skills and structured workflows.

# Basic Policies
- Respond in Japanese (code comments in English)
- Present a plan before implementation; proceed after approval
- Always run a verification command after creating files
- When errors occur, identify the root cause before fixing (never guess)

# Git
- Commit messages in English, Conventional Commits format
- Commit frequently per logical unit of work

# Coding Style
- Python: format with ruff, type hints required
- Use pathlib for file paths where practical
- Scripts must handle missing directories gracefully (create if needed)

# Commands
- `python -m pytest tests/ -v`: Run tests
- `python scripts/generate_pptx.py`: PowerPoint generation test
- `python scripts/generate_docx.py`: Word generation test

# Directory Structure
- `templates/`: Document templates (never overwrite)
- `output/`: Generated file output (gitignored)
- `.claude/skills/`: Project skill definitions
- `.claude/commands/`: Custom slash commands
- `scripts/`: Standalone generation scripts
- `tests/`: Test suite

# Important Rules
- Output filenames in output/ MUST include a datetime stamp
- NEVER overwrite template files
- Always verify generated files can be opened/parsed after creation
