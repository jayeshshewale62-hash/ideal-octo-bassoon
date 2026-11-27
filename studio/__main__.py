"""Allow ``python -m studio``."""

from __future__ import annotations

import sys

from studio.cli import main

sys.exit(main())
