"""
Main Flask server for image processing engine.
Handles image validation, storage, and PDF generation.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import sys
import sqlite3
import shutil
from datetime import datetime
from typing import Dict, List
import json
import time
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from validator import ImageValidator
from pdf_generator import PDFGenerator
from image_editor import apply_edits

app = Flask(__name__)
CORS(app)  # Enable CORS for Electron app

# Configuration
# Detect if running as PyInstaller bundle
def get_base_dir():
    """Get base directory for data files. Use writable location in production."""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle
        # Use user's home directory for data files
        import pathlib
        if sys.platform == 'darwin':
            # macOS: Use ~/Library/Application Support/Answer Sheet Scanner
            base = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'Answer Sheet Scanner')
        elif sys.platform == 'win32':
            # Windows: Use %APPDATA%/Answer Sheet Scanner
            base = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'Answer Sheet Scanner')
        else:
            # Linux: Use ~/.local/share/Answer Sheet Scanner
            base = os.path.join(os.path.expanduser('~'), '.local', 'share', 'Answer Sheet Scanner')
        os.makedirs(base, exist_ok=True)
        return base
    else:
        # Development mode: use script directory
        return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_dir()

WORKING_DIR = os.path.join(BASE_DIR, 'working')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')
DB_PATH = os.path.join(BASE_DIR, 'db', 'app.db')
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
SCANNER_WATCH_DIR = os.path.join(BASE_DIR, 'scanner_input')  # Folder to watch for scanned images
PORT = 5001  # Changed from 5000 to avoid conflicts
# Settings file path (in writable location)
SETTINGS_FILE = os.path.join(BASE_DIR, 'db', 'settings.json')

# Initialize components (will be updated after settings load)
validator = ImageValidator(hash_threshold=5)
pdf_generator = None  # Will be initialized after settings are loaded

# Global folder watcher observer
folder_observer = None

# Function to update PDF generator output directory
def update_pdf_generator_output_dir(new_dir):
    """Update PDF generator with new output directory."""
    global pdf_generator
    pdf_generator = PDFGenerator(output_dir=new_dir)

# Current answer copy state
current_answer_copy = {
    'id': None,
    'images': [],
    'working_path': None
}


def load_settings():
    """Load settings from local JSON file."""
    global OUTPUT_DIR, SCANNER_WATCH_DIR, pdf_generator
    
    default_settings = {
        'output_dir': OUTPUT_DIR,
        'scanner_watch_dir': SCANNER_WATCH_DIR
    }
    
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                # Update with saved settings if they exist
                if 'output_dir' in settings:
                    # Try to use saved path, create if doesn't exist
                    try:
                        if not os.path.isdir(settings['output_dir']):
                            os.makedirs(settings['output_dir'], exist_ok=True)
                        OUTPUT_DIR = settings['output_dir']
                    except Exception as e:
                        print(f"⚠️  Could not use saved output_dir: {e}. Using default.")
                
                if 'scanner_watch_dir' in settings:
                    # Try to use saved path, create if doesn't exist
                    try:
                        if not os.path.isdir(settings['scanner_watch_dir']):
                            os.makedirs(settings['scanner_watch_dir'], exist_ok=True)
                        SCANNER_WATCH_DIR = settings['scanner_watch_dir']
                    except Exception as e:
                        print(f"⚠️  Could not use saved scanner_watch_dir: {e}. Using default.")
                
                print(f"✓ Settings loaded from {SETTINGS_FILE}")
                print(f"  Output directory: {os.path.abspath(OUTPUT_DIR)}")
                print(f"  Scanner folder: {os.path.abspath(SCANNER_WATCH_DIR)}")
        except Exception as e:
            print(f"⚠️  Error loading settings: {e}. Using defaults.")
    else:
        # Create default settings file
        save_settings()
        print(f"✓ Created default settings file: {SETTINGS_FILE}")
    
    # Initialize PDF generator with loaded settings
    pdf_generator = PDFGenerator(output_dir=OUTPUT_DIR)


def save_settings():
    """Save current settings to local JSON file."""
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        # Save absolute paths for portability
        settings = {
            'output_dir': os.path.abspath(OUTPUT_DIR),
            'scanner_watch_dir': os.path.abspath(SCANNER_WATCH_DIR)
        }
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2)
        print(f"✓ Settings saved to {SETTINGS_FILE}")
    except Exception as e:
        print(f"⚠️  Error saving settings: {e}")


def init_database():
    """Initialize SQLite database."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS answer_copies (
            id TEXT PRIMARY KEY,
            created_at TIMESTAMP,
            completed_at TIMESTAMP,
            pdf_path TEXT,
            image_count INTEGER
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            answer_copy_id TEXT,
            image_path TEXT,
            image_hash TEXT,
            sequence_number INTEGER,
            uploaded_at TIMESTAMP,
            FOREIGN KEY (answer_copy_id) REFERENCES answer_copies(id)
        )
    ''')
    
    conn.commit()
    conn.close()


def generate_answer_copy_id() -> str:
    """Generate unique answer copy ID."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"AC_{timestamp}"


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'message': 'Image engine is running'})


@app.route('/start_answer_copy', methods=['POST'])
def start_answer_copy():
    """Start a new answer copy session."""
    global current_answer_copy
    
    # Reset validator
    validator.reset()
    
    # Generate new ID
    answer_copy_id = generate_answer_copy_id()
    working_path = os.path.join(WORKING_DIR, answer_copy_id)
    os.makedirs(working_path, exist_ok=True)
    
    # Update state
    current_answer_copy = {
        'id': answer_copy_id,
        'images': [],
        'working_path': working_path
    }
    
    # Store in database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO answer_copies (id, created_at, image_count)
        VALUES (?, ?, ?)
    ''', (answer_copy_id, datetime.now(), 0))
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'answer_copy_id': answer_copy_id,
        'message': 'New answer copy started'
    })


@app.route('/upload_image', methods=['POST'])
def upload_image():
    """Upload and validate an image."""
    global current_answer_copy
    
    if not current_answer_copy['id']:
        return jsonify({
            'success': False,
            'error': 'No active answer copy. Please start a new one first.'
        }), 400
    
    if 'image' not in request.files:
        return jsonify({
            'success': False,
            'error': 'No image file provided'
        }), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({
            'success': False,
            'error': 'Empty filename'
        }), 400
    
    # Save uploaded file temporarily
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    temp_path = os.path.join(UPLOAD_DIR, file.filename)
    file.save(temp_path)
    
    # Validate image
    validation_result = validator.validate_image(temp_path)
    
    if not validation_result['valid']:
        os.remove(temp_path)
        return jsonify({
            'success': False,
            'validation': validation_result
        }), 400
    
    # Image is valid - store it
    sequence_number = len(current_answer_copy['images']) + 1
    image_filename = f"page_{sequence_number:02d}.jpg"
    final_path = os.path.join(current_answer_copy['working_path'], image_filename)
    
    # Move to working directory
    shutil.move(temp_path, final_path)
    
    # Update state
    current_answer_copy['images'].append({
        'path': final_path,
        'sequence': sequence_number,
        'filename': image_filename
    })
    
    # Store in database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO images (answer_copy_id, image_path, sequence_number, uploaded_at)
        VALUES (?, ?, ?, ?)
    ''', (current_answer_copy['id'], final_path, sequence_number, datetime.now()))
    
    # Update answer copy count
    cursor.execute('''
        UPDATE answer_copies
        SET image_count = ?
        WHERE id = ?
    ''', (sequence_number, current_answer_copy['id']))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'validation': validation_result,
        'image': {
            'path': final_path,
            'sequence': sequence_number,
            'filename': image_filename
        },
        'total_images': sequence_number
    })


@app.route('/get_current_status', methods=['GET'])
def get_current_status():
    """Get current answer copy status."""
    global current_answer_copy
    
    if not current_answer_copy['id']:
        return jsonify({
            'active': False,
            'message': 'No active answer copy'
        })
    
    return jsonify({
        'active': True,
        'answer_copy_id': current_answer_copy['id'],
        'image_count': len(current_answer_copy['images']),
        'images': current_answer_copy['images']
    })


@app.route('/complete_answer_copy', methods=['POST'])
def complete_answer_copy():
    """Complete current answer copy and generate PDF."""
    global current_answer_copy
    
    if not current_answer_copy['id']:
        return jsonify({
            'success': False,
            'error': 'No active answer copy'
        }), 400
    
    if len(current_answer_copy['images']) == 0:
        return jsonify({
            'success': False,
            'error': 'No images in answer copy'
        }), 400
    
    try:
        # Get ordered image paths
        image_paths = [
            img['path'] for img in sorted(
                current_answer_copy['images'],
                key=lambda x: x['sequence']
            )
        ]
        
        # Generate PDF
        pdf_path = pdf_generator.generate_pdf(
            image_paths,
            current_answer_copy['id']
        )
        
        # Update database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE answer_copies
            SET completed_at = ?, pdf_path = ?
            WHERE id = ?
        ''', (datetime.now(), pdf_path, current_answer_copy['id']))
        conn.commit()
        conn.close()
        
        # Cleanup scanner folder
        cleanup_result = cleanup_scanner_folder_internal()
        
        # Reset state
        answer_copy_id = current_answer_copy['id']
        current_answer_copy = {
            'id': None,
            'images': [],
            'working_path': None
        }
        validator.reset()
        
        return jsonify({
            'success': True,
            'pdf_path': pdf_path,
            'answer_copy_id': answer_copy_id,
            'image_count': len(image_paths),
            'message': 'PDF generated successfully',
            'cleanup': cleanup_result
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'PDF generation failed: {str(e)}'
        }), 500


@app.route('/remove_image', methods=['POST'])
def remove_image():
    """Remove an image from current answer copy."""
    global current_answer_copy
    
    if not current_answer_copy['id']:
        return jsonify({
            'success': False,
            'error': 'No active answer copy'
        }), 400
    
    data = request.get_json()
    sequence = data.get('sequence')
    
    if not sequence:
        return jsonify({
            'success': False,
            'error': 'Sequence number required'
        }), 400
    
    # Find and remove image
    image_to_remove = None
    for img in current_answer_copy['images']:
        if img['sequence'] == sequence:
            image_to_remove = img
            break
    
    if not image_to_remove:
        return jsonify({
            'success': False,
            'error': 'Image not found'
        }), 404
    
    # Remove file
    if os.path.exists(image_to_remove['path']):
        os.remove(image_to_remove['path'])
    
    # Remove from state
    current_answer_copy['images'] = [
        img for img in current_answer_copy['images']
        if img['sequence'] != sequence
    ]
    
    # Renumber remaining images
    for idx, img in enumerate(sorted(current_answer_copy['images'], key=lambda x: x['sequence']), 1):
        old_path = img['path']
        new_filename = f"page_{idx:02d}.jpg"
        new_path = os.path.join(current_answer_copy['working_path'], new_filename)
        
        if old_path != new_path:
            os.rename(old_path, new_path)
            img['path'] = new_path
            img['sequence'] = idx
            img['filename'] = new_filename
    
    return jsonify({
        'success': True,
        'message': 'Image removed',
        'total_images': len(current_answer_copy['images'])
    })


@app.route('/set_scanner_folder', methods=['POST'])
def set_scanner_folder():
    """Set custom scanner folder to watch."""
    global SCANNER_WATCH_DIR, folder_observer
    data = request.get_json()
    folder_path = data.get('folder_path')
    
    if folder_path:
        # Create directory if it doesn't exist
        os.makedirs(folder_path, exist_ok=True)
        
        # Validate it's a directory
        if os.path.isdir(folder_path):
            # Stop existing observer if running
            if folder_observer:
                try:
                    folder_observer.stop()
                    folder_observer.join(timeout=1)
                except:
                    pass
            
            SCANNER_WATCH_DIR = folder_path
            
            # Save settings to file
            save_settings()
            
            # Restart folder watcher with new directory
            try:
                folder_observer = start_folder_watcher()
            except Exception as e:
                print(f"Warning: Could not restart folder watcher: {e}")
            
            return jsonify({
                'success': True,
                'message': f'Scanner folder set to: {folder_path}',
                'folder_path': os.path.abspath(folder_path)
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Invalid folder path'
            }), 400
    else:
        return jsonify({
            'success': False,
            'error': 'Folder path is required'
        }), 400


@app.route('/get_scanner_folder', methods=['GET'])
def get_scanner_folder():
    """Get current scanner folder path."""
    return jsonify({
        'folder_path': os.path.abspath(SCANNER_WATCH_DIR)
    })


@app.route('/get_output_folder', methods=['GET'])
def get_output_folder():
    """Get current output folder path."""
    return jsonify({
        'folder_path': os.path.abspath(OUTPUT_DIR)
    })


@app.route('/set_output_folder', methods=['POST'])
def set_output_folder():
    """Set custom output folder for PDFs."""
    global OUTPUT_DIR
    data = request.get_json()
    folder_path = data.get('folder_path')
    
    if folder_path:
        # Create directory if it doesn't exist
        os.makedirs(folder_path, exist_ok=True)
        
        # Validate it's a directory
        if os.path.isdir(folder_path):
            OUTPUT_DIR = folder_path
            # Update PDF generator with new output directory
            update_pdf_generator_output_dir(OUTPUT_DIR)
            # Save settings to file
            save_settings()
            return jsonify({
                'success': True,
                'message': f'Output folder set to: {folder_path}',
                'folder_path': os.path.abspath(folder_path)
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Invalid folder path'
            }), 400
    else:
        return jsonify({
            'success': False,
            'error': 'Folder path is required'
        }), 400


@app.route('/check_new_scanner_images', methods=['GET'])
def check_new_scanner_images():
    """Check for new images in scanner folder (for polling)."""
    if not current_answer_copy['id']:
        return jsonify({
            'new_images': [],
            'message': 'No active answer copy'
        })
    
    new_images = []
    if os.path.exists(SCANNER_WATCH_DIR):
        scanner_dir_abs = os.path.abspath(SCANNER_WATCH_DIR)
        for filename in os.listdir(SCANNER_WATCH_DIR):
            file_path = os.path.join(scanner_dir_abs, filename)
            if os.path.isfile(file_path):
                valid_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif')
                if filename.lower().endswith(valid_extensions):
                    # Check if not already processed
                    already_processed = any(
                        os.path.basename(img['path']) == filename 
                        for img in current_answer_copy['images']
                    )
                    if not already_processed:
                        new_images.append({
                            'path': file_path,
                            'filename': filename
                        })
    
    return jsonify({
        'new_images': new_images
    })


@app.route('/list_scanner_images', methods=['GET'])
def list_scanner_images():
    """List all images in scanner_input folder."""
    images = []
    if os.path.exists(SCANNER_WATCH_DIR):
        valid_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif')
        # Get absolute path of scanner directory
        scanner_dir_abs = os.path.abspath(SCANNER_WATCH_DIR)
        for filename in sorted(os.listdir(SCANNER_WATCH_DIR)):
            file_path = os.path.join(scanner_dir_abs, filename)
            if os.path.isfile(file_path) and filename.lower().endswith(valid_extensions):
                file_time = os.path.getmtime(file_path)
                images.append({
                    'filename': filename,
                    'path': file_path,
                    'created_at': datetime.fromtimestamp(file_time).isoformat()
                })
    
    # Sort by creation time (oldest first)
    images.sort(key=lambda x: x['created_at'])
    
    return jsonify({
        'images': images,
        'count': len(images)
    })


@app.route('/delete_scanner_image', methods=['POST'])
def delete_scanner_image():
    """Delete a single image from scanner_input folder."""
    data = request.get_json()
    image_path = data.get('path')
    
    if not image_path:
        return jsonify({
            'success': False,
            'error': 'Image path is required'
        }), 400
    
    # Validate that the path is within the scanner directory for security
    scanner_dir_abs = os.path.abspath(SCANNER_WATCH_DIR)
    image_path_abs = os.path.abspath(image_path)
    
    # Check if the image path is within the scanner directory
    if not image_path_abs.startswith(scanner_dir_abs):
        return jsonify({
            'success': False,
            'error': 'Invalid image path - must be within scanner folder'
        }), 400
    
    # Check if file exists
    if not os.path.exists(image_path_abs):
        return jsonify({
            'success': False,
            'error': 'Image file not found'
        }), 404
    
    try:
        # Delete the file
        os.remove(image_path_abs)
        return jsonify({
            'success': True,
            'message': 'Image deleted successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to delete image: {str(e)}'
        }), 500


@app.route('/list_pdfs', methods=['GET'])
def list_pdfs():
    """List all generated PDFs."""
    pdfs = []
    if os.path.exists(OUTPUT_DIR):
        # Get absolute path of output directory
        output_dir_abs = os.path.abspath(OUTPUT_DIR)
        for filename in sorted(os.listdir(OUTPUT_DIR), reverse=True):
            if filename.lower().endswith('.pdf'):
                file_path = os.path.join(output_dir_abs, filename)
                file_size = os.path.getsize(file_path)
                file_time = os.path.getmtime(file_path)
                pdfs.append({
                    'filename': filename,
                    'path': file_path,
                    'size': file_size,
                    'size_mb': round(file_size / (1024 * 1024), 2),
                    'created_at': datetime.fromtimestamp(file_time).isoformat()
                })
    
    return jsonify({
        'pdfs': pdfs,
        'count': len(pdfs)
    })


def cleanup_scanner_folder_internal():
    """Internal function to cleanup scanner folder."""
    deleted_count = 0
    errors = []
    
    if os.path.exists(SCANNER_WATCH_DIR):
        for filename in os.listdir(SCANNER_WATCH_DIR):
            file_path = os.path.join(SCANNER_WATCH_DIR, filename)
            if os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                    deleted_count += 1
                except Exception as e:
                    errors.append(f"Failed to delete {filename}: {str(e)}")
    
    return {
        'deleted_count': deleted_count,
        'errors': errors
    }


@app.route('/cleanup_scanner_folder', methods=['POST'])
def cleanup_scanner_folder():
    """Delete all images from scanner folder."""
    result = cleanup_scanner_folder_internal()
    return jsonify({
        'success': True,
        **result
    })


@app.route('/apply_image_edits', methods=['POST'])
def apply_image_edits_endpoint():
    """Apply edits to an image."""
    global current_answer_copy
    
    if not current_answer_copy['id']:
        return jsonify({
            'success': False,
            'error': 'No active answer copy'
        }), 400
    
    try:
        data = request.get_json()
        sequence = data.get('sequence')
        edits = data.get('edits', {})
        
        # Find image
        image_data = next(
            (img for img in current_answer_copy['images'] if img['sequence'] == sequence),
            None
        )
        
        if not image_data:
            return jsonify({
                'success': False,
                'error': 'Image not found'
            }), 404
        
        # Apply edits
        edited_path = apply_edits(image_data['path'], edits)
        
        return jsonify({
            'success': True,
            'message': 'Edits applied',
            'image_path': edited_path
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/save_edited_image', methods=['POST'])
def save_edited_image():
    """Save an edited image (from base64 or file)."""
    global current_answer_copy
    
    if not current_answer_copy['id']:
        return jsonify({
            'success': False,
            'error': 'No active answer copy'
        }), 400
    
    try:
        if 'image' in request.files:
            # File upload
            file = request.files['image']
            sequence = request.form.get('sequence', type=int)
            
            if sequence:
                # Replace existing image
                existing_img = next(
                    (img for img in current_answer_copy['images'] if img['sequence'] == sequence),
                    None
                )
                if existing_img:
                    file.save(existing_img['path'])
                    return jsonify({
                        'success': True,
                        'message': 'Image saved',
                        'image': existing_img
                    })
            
            # New image
            sequence_number = len(current_answer_copy['images']) + 1
            image_filename = f"page_{sequence_number:02d}.jpg"
            final_path = os.path.join(current_answer_copy['working_path'], image_filename)
            file.save(final_path)
            
            current_answer_copy['images'].append({
                'path': final_path,
                'sequence': sequence_number,
                'filename': image_filename
            })
            
            return jsonify({
                'success': True,
                'message': 'Image saved',
                'image': {
                    'path': final_path,
                    'sequence': sequence_number,
                    'filename': image_filename
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No image provided'
            }), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


class ScannerFileHandler(FileSystemEventHandler):
    """Handles file system events for scanner folder."""
    
    def __init__(self):
        self.processed_files = set()
    
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
            target=process_scanner_image,
            args=(file_path,),
            daemon=True
        ).start()


def process_scanner_image(image_path: str):
    """Process an image from the scanner folder."""
    global current_answer_copy
    
    if not current_answer_copy['id']:
        print(f"⚠️  No active answer copy. Image ignored: {image_path}")
        return
    
    try:
        # Validate image
        validation_result = validator.validate_image(image_path)
        
        if not validation_result['valid']:
            print(f"❌ Image validation failed: {image_path}")
            print(f"   Reason: {validation_result.get('message', 'Unknown error')}")
            return
        
        # Image is valid - store it
        sequence_number = len(current_answer_copy['images']) + 1
        image_filename = f"page_{sequence_number:02d}.jpg"
        final_path = os.path.join(current_answer_copy['working_path'], image_filename)
        
        # Copy to working directory
        shutil.copy2(image_path, final_path)
        
        # Update state
        current_answer_copy['images'].append({
            'path': final_path,
            'sequence': sequence_number,
            'filename': image_filename
        })
        
        # Store in database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO images (answer_copy_id, image_path, sequence_number, uploaded_at)
            VALUES (?, ?, ?, ?)
        ''', (current_answer_copy['id'], final_path, sequence_number, datetime.now()))
        
        # Update answer copy count
        cursor.execute('''
            UPDATE answer_copies
            SET image_count = ?
            WHERE id = ?
        ''', (sequence_number, current_answer_copy['id']))
        
        conn.commit()
        conn.close()
        
        print(f"✅ Scanner image processed: {image_filename} (Sequence: {sequence_number})")
        
        # Optionally move processed file to archive
        # archive_path = os.path.join(SCANNER_WATCH_DIR, 'processed', os.path.basename(image_path))
        # os.makedirs(os.path.dirname(archive_path), exist_ok=True)
        # shutil.move(image_path, archive_path)
        
    except Exception as e:
        print(f"❌ Error processing scanner image {image_path}: {str(e)}")


def start_folder_watcher():
    """Start watching the scanner folder for new images."""
    observer = Observer()
    event_handler = ScannerFileHandler()
    observer.schedule(event_handler, SCANNER_WATCH_DIR, recursive=False)
    observer.start()
    print(f"📁 Watching scanner folder: {os.path.abspath(SCANNER_WATCH_DIR)}")
    print(f"   Place scanned images in this folder to auto-import them")
    return observer


if __name__ == '__main__':
    # Initialize database (creates db directory if needed)
    init_database()
    
    # Load saved settings (must be before creating directories and initializing components)
    load_settings()
    
    # Ensure pdf_generator is initialized with loaded settings
    if pdf_generator is None:
        pdf_generator = PDFGenerator(output_dir=OUTPUT_DIR)
    else:
        # Update if already exists (shouldn't happen, but just in case)
        update_pdf_generator_output_dir(OUTPUT_DIR)
    
    # Create necessary directories
    os.makedirs(WORKING_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    # Create scanner watch directory
    os.makedirs(SCANNER_WATCH_DIR, exist_ok=True)
    
    # Start folder watcher for scanner integration (uses loaded SCANNER_WATCH_DIR)
    folder_observer = start_folder_watcher()
    
    try:
        # Run Flask server
        print(f"Starting Image Engine Server on http://127.0.0.1:{PORT}")
        app.run(host='127.0.0.1', port=PORT, debug=False)
    except KeyboardInterrupt:
        print("\nShutting down...")
        if folder_observer:
            folder_observer.stop()
    if folder_observer:
        folder_observer.join()
