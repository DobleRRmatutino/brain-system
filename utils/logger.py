import logging
from datetime import datetime
from pathlib import Path

LOG_PATH = Path("./logs")

def get_logger(name: str = "brain-system") -> logging.Logger:
    LOG_PATH.mkdir(exist_ok=True)
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))

    today = datetime.now().strftime("%Y%m%d")
    file_handler = logging.FileHandler(LOG_PATH / f"{today}.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

    logger.addHandler(console)
    logger.addHandler(file_handler)
    return logger
