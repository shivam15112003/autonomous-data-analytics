# Contributing

Thanks for your interest in improving this project.

## Development setup
1. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -U pip
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-optional.txt
   ```

## Pull request checklist
- [ ] Add/update docs in `docs/` for user-facing changes
- [ ] Keep secrets out of the repo (`gemini_api_key.txt` is ignored)
- [ ] Ensure the script still runs in `--gemini-mode off`
- [ ] If adding new dependencies, list them in the appropriate requirements file
