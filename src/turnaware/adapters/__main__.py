"""CLI entry for the adapter tier: `python -m turnaware.adapters`.

Defaults to the channel adapter (the only adapter shipped today).
"""

import sys

from .channel import main

if __name__ == "__main__":
    sys.exit(main())
