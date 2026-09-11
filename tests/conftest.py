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
