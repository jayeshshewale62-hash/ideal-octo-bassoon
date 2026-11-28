# Test fixtures

Most fixtures are generated at runtime by `tests/conftest.py` (the `samples` fixture builds
valid SVG, PNG, WAV, MP3, JSON and YAML files in a temporary directory). This keeps binary
files out of git. Put small, hand-written text fixtures here when a test needs a fixed file.
