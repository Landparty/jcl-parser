"""Allow running jclparser as ``python -m jclparser``."""

from .cli import main

raise SystemExit(main())
