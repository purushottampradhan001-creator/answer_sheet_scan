"""
Scanner folder watcher service
"""

import os
import time
import shutil
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from typing import Optional, Callable

# Use absolute imports - ensure project root is in sys.path
import sys
import os

# Add project root to path if not already there
_current_file = os.path.abspath(__file__)
_src_dir = os.path.dirname(os.path.dirname(_current_file))
_project_dir = os.path.dirname(_src_dir)
if _project_dir not in sys.path:
    sys.path.insert(0, _project_dir)

from src.services.image_validator import ImageValidator
from src.models.answer_copy import AnswerCopy
from src.models.database import Database
from src.utils.image_utils import extract_unique_id_from_image


class ScannerFileHandler(FileSystemEventHandler):
    """Handles file system events for scanner folder."""
    
    def __init__(self, on_image_detected: Callable):
        self.processed_files = set()
        self.on_image_detected = on_image_detected
    
    def on_created(self, event):
        """Called when a new file is created in the watched folder."""
        if event.is_directory:
            return
        
        # Wait a bit for file to be fully written
        time.sleep(0.5)
        
        file_path = event.src_path
        
        # Check if it's an image file
        valid_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif')
        if not file_path.lower().endswith(valid_extensions):
            return
        
        # Avoid processing the same file twice
        if file_path in self.processed_files:
            return
        
        # Check if file exists and is readable
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            return
        
        self.processed_files.add(file_path)
        
        # Process the image in a separate thread
        threading.Thread(
            target=self.on_image_detected,
            args=(file_path,),
            daemon=True
        ).start()


class ScannerWatcher:
    """Manages scanner folder watching"""
    
    def __init__(self, scanner_dir: str, validator: ImageValidator, 
                 current_answer_copy: Optional[AnswerCopy], db: Database):
        self.scanner_dir = scanner_dir
        self.validator = validator
        self.current_answer_copy = current_answer_copy
        self.db = db
        self.observer: Optional[Observer] = None
    
    def start(self):
        """Start watching the scanner folder for new images."""
        if not os.path.exists(self.scanner_dir):
            os.makedirs(self.scanner_dir, exist_ok=True)
        
        self.observer = Observer()
        event_handler = ScannerFileHandler(self._process_scanner_image)
        self.observer.schedule(event_handler, self.scanner_dir, recursive=False)
        self.observer.start()
        print(f"📁 Watching scanner folder: {os.path.abspath(self.scanner_dir)}")
        print(f"   Place scanned images in this folder to auto-import them")
    
    def stop(self):
        """Stop watching the scanner folder."""
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=1)
    
    def update_answer_copy(self, answer_copy: Optional[AnswerCopy]):
        """Update the current answer copy reference."""
        self.current_answer_copy = answer_copy
    
    def _process_scanner_image(self, image_path: str):
        """Process an image from the scanner folder."""
        if not self.current_answer_copy:
            print(f"⚠️  No active answer copy. Image ignored: {image_path}")
            return
        
        try:
            # Validate image
            validation_result = self.validator.validate_image(image_path)
            
            if not validation_result['valid']:
                print(f"❌ Image validation failed: {image_path}")
                print(f"   Reason: {validation_result.get('message', 'Unknown error')}")
                return
            
            # Image is valid - store it
            sequence_number = len(self.current_answer_copy.images) + 1
            image_filename = f"page_{sequence_number:02d}.jpg"
            final_path = os.path.join(self.current_answer_copy.working_path, image_filename)
            
            # Copy to working directory
            shutil.copy2(image_path, final_path)
            
            # Update state
            self.current_answer_copy.add_image(final_path, sequence_number, image_filename)
            
            # Store in database
            self.db.add_image(
                self.current_answer_copy.id,
                final_path,
                sequence_number
            )
            
            # If this is the first image and unique_id is not set, extract it
            if sequence_number == 1 and not self.current_answer_copy.exam_details.get('unique_id'):
                unique_id = extract_unique_id_from_image(final_path)
                if unique_id:
                    self.current_answer_copy.exam_details['unique_id'] = unique_id
                    print(f"📝 Unique ID extracted from first page: {unique_id}")
            
            print(f"✅ Scanner image processed: {image_filename} (Sequence: {sequence_number})")
            
        except Exception as e:
            print(f"❌ Error processing scanner image {image_path}: {str(e)}")
