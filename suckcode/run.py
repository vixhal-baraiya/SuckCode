#!/usr/bin/env python3
"""Run suckcode - works from any directory."""

import sys
from pathlib import Path

# Add parent to path if running from inside package
if __name__ == "__main__":
    pkg_dir = Path(__file__).parent
    parent_dir = pkg_dir.parent
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))
    
    from suckcode.suckcode import main
    main()
