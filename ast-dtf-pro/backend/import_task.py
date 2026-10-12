"""One-shot file parser isolated from API process with Unix resource limits."""
import json
import resource
import sys
from pathlib import Path
from .vector_io import ingest

if __name__=='__main__':
    resource.setrlimit(resource.RLIMIT_CPU,(50,55))
    resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE,(100*1024**2,100*1024**2))
    try:
        result=ingest(Path(sys.argv[1]).read_bytes(),sys.argv[2],sys.argv[3])
        Path(sys.argv[4]).write_text(json.dumps({'assets':result}))
    except Exception as exc:
        Path(sys.argv[4]).write_text(json.dumps({'error':str(exc)}));sys.exit(2)
