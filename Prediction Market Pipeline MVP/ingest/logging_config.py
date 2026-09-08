import logging
import os

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "pipeline.log")


def get_logger(name):
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger(name)
    if not logger.handlers:   # don't stack duplicate handlers if called more than once
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")

        file_handler = logging.FileHandler(LOG_FILE)   # appends across runs
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()       # still shows up in GitHub Actions logs
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    return logger
