import sys
import os

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, '..'))
SERVER_DIR = os.path.join(ROOT_DIR, 'server')
sys.path.insert(0, SERVER_DIR)

import db
from app import DinoJumpHandler

class handler(DinoJumpHandler):
    pass
