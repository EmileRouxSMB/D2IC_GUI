"""Start D2IC_GUI on loopback: python -m D2IC_GUI [study_folder]."""
import sys
import uvicorn
from .server import create_app

if __name__ == '__main__':
    uvicorn.run(create_app(sys.argv[1] if len(sys.argv)>1 else None),
                host='127.0.0.1', port=8765, log_level='info')
