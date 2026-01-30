# EduBag

Python tools for Bootstrapping, Aggregating, and Gathering learner data

* PyPI package: https://pypi.org/project/python-edubag/
* Free software: MIT License
* Documentation: https://leingang.github.io/python-edubag/.

## Features

* TODO

## Development

### Setup

1. Clone the repository and navigate to it:
   ```bash
   git clone https://github.com/leingang/python-edubag.git
   cd python-edubag
   ```

2. Install dependencies with `uv`:
   ```bash
   uv sync --all-extras
   ```

3. Activate the virtual environment:
   ```bash
   source .venv/bin/activate  # macOS/Linux
   .venv\Scripts\activate.bat  # Windows (cmd)
   .venv\Scripts\Activate.ps1  # Windows (PowerShell)
   ```

### Running Tests

Run the test suite with `pytest`:

```bash
pytest                           # Run all tests
pytest tests/test_file.py        # Run specific test file
pytest -v                        # Verbose output
```

Or use `uv run` to run without activating the venv:

```bash
uv run pytest
uv run pytest tests/test_file.py -v
```

### Building Documentation

The documentation is built with [MkDocs](https://www.mkdocs.org/). To build and serve the documentation locally:

```bash
mkdocs serve
```

This will start a local server at `http://127.0.0.1:8000` and watch for changes.

To build the static site without serving:

```bash
mkdocs build
```

The built site will be in the `site/` directory.

## Credits

This package was created with [Cookiecutter](https://github.com/audreyfeldroy/cookiecutter) and the [audreyfeldroy/cookiecutter-pypackage](https://github.com/audreyfeldroy/cookiecutter-pypackage) project template.
