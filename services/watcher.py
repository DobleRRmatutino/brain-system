import time
import sys
import threading
from pathlib import Path
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler
from utils.logger import get_logger

logger = get_logger()

# Timers activos por archivo
_timers = {}

def process_file(path: Path):
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        logger.warning(f"Empty note, skipping: {path.name}")
        return
    logger.info(f"Processing: {path.name} ({len(content)} chars)")
    try:
        from main import process
        result = process(content)
        print(f"✅ {result['title']} → Notion")
    except Exception as e:
        logger.error(f"Error processing {path.name}: {e}")

class InboxHandler(FileSystemEventHandler):
    def handle(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix != ".md":
            return

        # Cancelar timer anterior si existe
        if path.name in _timers:
            _timers[path.name].cancel()

        # Nuevo timer de 30s
        logger.info(f"📝 Change detected: {path.name} (waiting 30s...)")
        timer = threading.Timer(30, process_file, args=[path])
        _timers[path.name] = timer
        timer.start()

    def on_created(self, event):
        self.handle(event)

    def on_modified(self, event):
        self.handle(event)

def start_watcher(inbox_path: str):
    path = Path(inbox_path)
    if not path.exists():
        logger.error(f"Inbox not found: {inbox_path}")
        sys.exit(1)

    logger.info(f"👀 Watching (polling): {inbox_path}")
    handler = InboxHandler()
    observer = PollingObserver()
    observer.schedule(handler, str(path), recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        for t in _timers.values():
            t.cancel()
        logger.info("Watcher stopped.")
    observer.join()

if __name__ == "__main__":
    from config.settings import INBOX_PATH
    start_watcher(INBOX_PATH)
