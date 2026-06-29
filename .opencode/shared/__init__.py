""".opencode/shared/ — novel-create-hermes 工具脚本包

所有可执行脚本集中在此目录。技能包通过 `python .opencode/shared/{name}.py` 调用。
此 __init__.py 确保模块可被正确导入，无论工作目录在哪。
"""

import sys
from pathlib import Path

_THIS_DIR = Path(__file__).parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))
