"""Make the stamped module tree importable without stamping it.

The modules under test ship as skill templates, not as an installed package.
Putting `templates/adws` on sys.path lets the tests import `adw_modules.*`
exactly as a stamped repo would, so what we test is what gets shipped.
"""

import sys
from pathlib import Path

TEMPLATES_ADWS = (Path(__file__).resolve().parent.parent
                  / ".claude" / "skills" / "sssf" / "templates" / "adws")

if str(TEMPLATES_ADWS) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_ADWS))

TEMPLATES = TEMPLATES_ADWS.parent          # .../skills/sssf/templates

if str(TEMPLATES) not in sys.path:
    sys.path.insert(0, str(TEMPLATES))

# A framework's gate module is stamped INTO adw_modules at install time, and it
# imports its siblings relatively (`from .data_types import ...`). Extending the
# package's search path is what lets a test import it under its real stamped
# name, with its real package context, straight from the source - so what the
# tests exercise is the file that ships, not a copy of it.
import adw_modules  # noqa: E402

PROFILE_GATES_SRC = TEMPLATES / "profiles" / "gates"

if str(PROFILE_GATES_SRC) not in adw_modules.__path__:
    adw_modules.__path__.append(str(PROFILE_GATES_SRC))
