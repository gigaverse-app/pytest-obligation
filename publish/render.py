"""Container entry point: trusted imports, data-only archive, Markdown on captured stdout."""

import sys
from pathlib import Path

# -I excludes the working directory and environment. This is image-owned source, never PR input.
sys.path.insert(0, "/opt/reporter")
from pytest_obligation.reporting.republish import main  # noqa: E402

main(["--artifact", "/input/evidence.zip", "--output", "/tmp/report.md", *sys.argv[1:]])
sys.stdout.write(Path("/tmp/report.md").read_text(encoding="utf-8"))
