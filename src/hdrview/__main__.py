"""支持 python -m hdrview，所有命令仍由同一入口解析。"""

from hdrview.cli import main

raise SystemExit(main())
