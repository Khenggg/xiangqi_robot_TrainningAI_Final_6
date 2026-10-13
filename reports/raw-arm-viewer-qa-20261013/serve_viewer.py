from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root))
from src.core.launch_options import ViewerServer
server=ViewerServer(root,8089)
server.server.serve_forever()
