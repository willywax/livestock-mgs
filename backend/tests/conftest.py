import os
import sys

# Allow "import models", "import server", etc. regardless of cwd.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
