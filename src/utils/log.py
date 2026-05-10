import io
import sys
import logging
from logging.handlers import RotatingFileHandler
import os
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Define the log levels and their corresponding file names
LOG_LEVELS = {
    'DEBUG': 'debug.log',
    'INFO': 'info.log',
    'ERROR': 'error.log'
}

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Define the log format
log_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Create logs directory if not exists
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
log_dir = os.path.join(BASE_DIR, "logs")

if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Function to get dated log file path
def get_log_file(level):
    today = datetime.now().strftime('%Y-%m-%d')
    dated_log_dir = os.path.join(log_dir, today)
    if not os.path.exists(dated_log_dir):
        os.makedirs(dated_log_dir)
    return os.path.join(dated_log_dir, LOG_LEVELS[level])

# Custom filter to allow only specific level
class LevelFilter(logging.Filter):
    def __init__(self, level):
        super().__init__()
        self.level = level
    def filter(self, record):
        return record.levelno == self.level

# Create handlers for each log level
for level_name in LOG_LEVELS:
    level = getattr(logging, level_name)
    handler = RotatingFileHandler(get_log_file(level_name), maxBytes=10*1024*1024, backupCount=5)
    handler.setLevel(logging.DEBUG)  # keep low, filtering will decide
    handler.setFormatter(log_format)
    handler.addFilter(LevelFilter(level))  # ensure only exact level goes here
    logger.addHandler(handler)
