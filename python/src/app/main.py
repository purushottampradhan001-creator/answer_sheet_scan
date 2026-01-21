"""
Main Flask application entry point
"""

import sys
import os
import traceback
import logging 

# Set up logging - output to stderr so it's captured by Electron
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)
# Add project root to path for imports
# This allows 'src.*' imports to work when running the script directly
_current_dir = os.path.dirname(os.path.abspath(__file__))
_src_dir = os.path.dirname(_current_dir)
_project_dir = os.path.dirname(_src_dir)

# Add project root to Python path so src.* imports work
if _project_dir not in sys.path:
    sys.path.insert(0, _project_dir)

from flask import Flask, request, jsonify
from flask_cors import CORS
import shutil
import sqlite3
from datetime import datetime
from typing import Dict
from PIL import Image

# Use absolute imports with src.* prefix
from src.app.config import config
from src.models.database import Database
from src.models.answer_copy import AnswerCopy
from src.services.image_validator import ImageValidator
from src.services.pdf_generator import PDFGenerator
from src.services.scanner_watcher import ScannerWatcher
from src.services.auto_image_processor import AutoImageProcessor
from src.utils.file_utils import generate_answer_copy_id, list_images_in_directory, list_pdfs_in_directory, sanitize_filename
from src.utils.image_utils import extract_unique_id_from_image, generate_unique_id_from_fields
from src.services.image_editor import apply_edits

# Import all route handlers - we'll create these as blueprints
# For now, we'll define routes directly here to maintain functionality

app = Flask(__name__)
CORS(app)

# Initialize components
validator = ImageValidator(hash_threshold=5)
pdf_generator = PDFGenerator(output_dir=config.output_dir)
auto_processor = AutoImageProcessor()
db = Database(config.db_path)

# Global state for current answer copy
current_answer_copy: AnswerCopy = None
scanner_watcher = ScannerWatcher(
    config.scanner_watch_dir,
    validator,
    current_answer_copy,
    db
)

# Make scanner_watcher available globally
_scanner_watcher_instance = scanner_watcher


def safe_strip(value):
    """Safely strip a value, handling None."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    return str(value).strip() or None


def auto_process_uploaded_image(image_path: str) -> Dict:
    """
    Automatically process uploaded image with all auto-processing features.
    
    Args:
        image_path: Path to the image file
    
    Returns:
        Dictionary with processing results and messages (from auto_processor.auto_process)
    """
    try:
        # Run auto processing with all checks and fixes
        # Messages are already built in auto_process function
        auto_result = auto_processor.auto_process(image_path, auto_fix=True)
        # Debug print so backend console shows the "answer" (processing outcome)
        try:
            print(
                f"🧾 [auto_process_uploaded_image] {os.path.basename(image_path)} "
                f"-> processed={os.path.basename(auto_result.get('processed_image_path', '') or '')} "
                f"fixes={auto_result.get('fixes_applied', [])} "
                f"warnings={len(auto_result.get('warnings', []) or [])} "
                f"needs_attention={bool(auto_result.get('needs_attention'))}"
                , flush=True
            )
            msgs = auto_result.get('messages') or []
            if msgs:
                print("🧾 [auto_process_uploaded_image] messages:", " | ".join(map(str, msgs)), flush=True)
        except Exception:
            pass
        return auto_result
    except Exception as e:
        return {
            'messages': [f"❌ Error during auto-processing: {str(e)}"],
            'checks': {},
            'fixes_applied': [],
            'needs_attention': True,
            'warnings': [f"Error: {str(e)}"],
            'error': str(e)
        }


def cleanup_scanner_folder_internal():
    """Internal function to cleanup scanner folder - only removes images, not PDFs."""
    deleted_count = 0
    errors = []
    
    # Image extensions to clean (same as in file_utils.py)
    valid_image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif')
    
    if os.path.exists(config.scanner_watch_dir):
        for filename in os.listdir(config.scanner_watch_dir):
            file_path = os.path.join(config.scanner_watch_dir, filename)
            if os.path.isfile(file_path):
                # Only delete image files, skip PDFs and other files
                if filename.lower().endswith(valid_image_extensions):
                    try:
                        os.remove(file_path)
                        deleted_count += 1
                    except Exception as e:
                        errors.append(f"Failed to delete {filename}: {str(e)}")
    
    return {
        'deleted_count': deleted_count,
        'errors': errors
    }


# Health check
@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'message': 'Image engine is running'})


# Answer copy routes
@app.route('/start_answer_copy', methods=['POST'])
def start_answer_copy():
    """Start a new answer copy session."""
    global current_answer_copy
    
    # Reset validator
    validator.reset()
    
    # Generate new ID
    answer_copy_id = generate_answer_copy_id()
    working_path = os.path.join(config.working_dir, answer_copy_id)
    os.makedirs(working_path, exist_ok=True)
    
    # Load exam details from saved settings (automatically restore on reopen)
    # If there's a current answer copy, preserve its exam_details, otherwise load from settings
    if current_answer_copy and current_answer_copy.exam_details and any([
        current_answer_copy.exam_details.get('degree'),
        current_answer_copy.exam_details.get('subject'),
        current_answer_copy.exam_details.get('exam_date'),
        current_answer_copy.exam_details.get('college')
    ]):
        # Use current exam details if they exist
        saved_exam_details = current_answer_copy.exam_details.copy()
    else:
        # Load from saved settings file
        saved_exam_details = config.get_saved_exam_details()
    
    # Create new answer copy
    current_answer_copy = AnswerCopy(answer_copy_id, working_path)
    current_answer_copy.exam_details = saved_exam_details.copy()
    
    # Update scanner watcher
    scanner_watcher.update_answer_copy(current_answer_copy)
    
    # Store in database
    db.create_answer_copy(answer_copy_id)
    
    return jsonify({
        'success': True,
        'answer_copy_id': answer_copy_id,
        'message': 'New answer copy started',
        'exam_details': current_answer_copy.exam_details
    })


@app.route('/get_current_status', methods=['GET'])
def get_current_status():
    """Get current answer copy status."""
    global current_answer_copy
    
    if not current_answer_copy or not current_answer_copy.id:
        return jsonify({
            'active': False,
            'message': 'No active answer copy'
        })
    
    return jsonify({
        'active': True,
        'answer_copy_id': current_answer_copy.id,
        'image_count': len(current_answer_copy.images),
        'images': current_answer_copy.images,
        'exam_details': current_answer_copy.exam_details
    })


@app.route('/upload_image', methods=['POST'])
def upload_image():
    """Upload and validate an image."""
    global current_answer_copy
    
    if not current_answer_copy or not current_answer_copy.id:
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
    os.makedirs(config.upload_dir, exist_ok=True)
    temp_path = os.path.join(config.upload_dir, file.filename)
    file.save(temp_path)
    
    # Validate image (with auto checks)
    validation_result = validator.validate_image(temp_path, include_auto_checks=True)
    
    if not validation_result['valid']:
        os.remove(temp_path)
        return jsonify({
            'success': False,
            'validation': validation_result
        }), 400
    
    # Auto-process image (apply all fixes automatically)
    auto_processing_result = auto_process_uploaded_image(temp_path)
    
    # Image is valid - store it
    sequence_number = len(current_answer_copy.images) + 1
    image_filename = f"page_{sequence_number:02d}.jpg"
    final_path = os.path.join(current_answer_copy.working_path, image_filename)
    
    # Move processed image to working directory
    shutil.move(temp_path, final_path)
    
    # Update state
    current_answer_copy.add_image(final_path, sequence_number, image_filename)
    
    # Store in database
    db.add_image(current_answer_copy.id, final_path, sequence_number)
    
    # If this is the first image and unique_id is not set, extract it
    if sequence_number == 1 and not current_answer_copy.exam_details.get('unique_id'):
        unique_id = extract_unique_id_from_image(final_path)
        if unique_id:
            current_answer_copy.exam_details['unique_id'] = unique_id
    
    return jsonify({
        'success': True,
        'validation': validation_result,
        'auto_processing': auto_processing_result,
        'image': {
            'path': final_path,
            'sequence': sequence_number,
            'filename': image_filename
        },
        'total_images': sequence_number,
        'unique_id_extracted': sequence_number == 1 and current_answer_copy.exam_details.get('unique_id') is not None
    })


@app.route('/complete_answer_copy', methods=['POST'])
def complete_answer_copy():
    """Complete current answer copy and generate PDF."""
    global current_answer_copy
    
    if not current_answer_copy or not current_answer_copy.id:
        return jsonify({
            'success': False,
            'error': 'No active answer copy'
        }), 400
    
    if len(current_answer_copy.images) == 0:
        return jsonify({
            'success': False,
            'error': 'No images in answer copy'
        }), 400
    
    try:
        # Get ordered image paths
        image_paths = current_answer_copy.get_ordered_images()
        
        # Generate PDF
        pdf_path = pdf_generator.generate_pdf(
            image_paths,
            current_answer_copy.id,
            exam_details=current_answer_copy.exam_details
        )
        
        # Update database
        db.complete_answer_copy(current_answer_copy.id, pdf_path)
        
        # Cleanup scanner folder
        cleanup_result = cleanup_scanner_folder_internal()
        
        # Reset state
        answer_copy_id = current_answer_copy.id
        current_answer_copy = None
        scanner_watcher.update_answer_copy(None)
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
    
    if not current_answer_copy or not current_answer_copy.id:
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
    for img in current_answer_copy.images:
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
    current_answer_copy.images = [
        img for img in current_answer_copy.images
        if img['sequence'] != sequence
    ]
    
    # Renumber remaining images
    for idx, img in enumerate(sorted(current_answer_copy.images, key=lambda x: x['sequence']), 1):
        old_path = img['path']
        new_filename = f"page_{idx:02d}.jpg"
        new_path = os.path.join(current_answer_copy.working_path, new_filename)
        
        if old_path != new_path:
            os.rename(old_path, new_path)
            img['path'] = new_path
            img['sequence'] = idx
            img['filename'] = new_filename
    
    return jsonify({
        'success': True,
        'message': 'Image removed',
        'total_images': len(current_answer_copy.images)
    })


# Settings routes
@app.route('/get_scanner_folder', methods=['GET'])
def get_scanner_folder():
    """Get current scanner folder path."""
    return jsonify({
        'folder_path': os.path.abspath(config.scanner_watch_dir)
    })


@app.route('/set_scanner_folder', methods=['POST'])
def set_scanner_folder():
    """Set custom scanner folder to watch."""
    global scanner_watcher
    data = request.get_json()
    folder_path = data.get('folder_path')
    
    if folder_path:
        os.makedirs(folder_path, exist_ok=True)
        
        if os.path.isdir(folder_path):
            # Stop existing watcher
            scanner_watcher.stop()
            
            # Update config
            config.scanner_watch_dir = folder_path
            config.save_settings()
            
            # Create new watcher
            scanner_watcher = ScannerWatcher(
                config.scanner_watch_dir,
                validator,
                current_answer_copy,
                db
            )
            scanner_watcher.start()
            
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


@app.route('/get_output_folder', methods=['GET'])
def get_output_folder():
    """Get current output folder path."""
    return jsonify({
        'folder_path': os.path.abspath(config.output_dir)
    })


@app.route('/set_output_folder', methods=['POST'])
def set_output_folder():
    """Set custom output folder for PDFs."""
    data = request.get_json()
    folder_path = data.get('folder_path')
    
    if folder_path:
        os.makedirs(folder_path, exist_ok=True)
        
        if os.path.isdir(folder_path):
            config.output_dir = folder_path
            global pdf_generator
            pdf_generator = PDFGenerator(output_dir=config.output_dir)
            config.save_settings()
            
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


# Image routes
@app.route('/list_scanner_images', methods=['GET'])
def list_scanner_images():
    """List all images in scanner_input folder."""
    images = list_images_in_directory(config.scanner_watch_dir)
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
    scanner_dir_abs = os.path.abspath(config.scanner_watch_dir)
    image_path_abs = os.path.abspath(image_path)
    
    if not image_path_abs.startswith(scanner_dir_abs):
        return jsonify({
            'success': False,
            'error': 'Invalid image path - must be within scanner folder'
        }), 400
    
    if not os.path.exists(image_path_abs):
        return jsonify({
            'success': False,
            'error': 'Image file not found'
        }), 404
    
    try:
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


@app.route('/apply_scanner_image_edits', methods=['POST'])
def apply_scanner_image_edits():
    """Apply edits directly to an image in the scanner_input folder."""
    data = request.get_json()
    image_path = data.get('image_path')
    edits = data.get('edits', {})

    if not image_path:
        return jsonify({
            'success': False,
            'error': 'Image path is required'
        }), 400

    # Normalize the path - remove file:// prefix if present, normalize separators
    if image_path.startswith('file://'):
        image_path = image_path[7:]
    image_path = os.path.normpath(image_path)

    # Validate that the path is within the scanner directory for security
    scanner_dir_abs = os.path.abspath(config.scanner_watch_dir)
    image_path_abs = os.path.abspath(image_path)

    if not image_path_abs.startswith(scanner_dir_abs):
        return jsonify({
            'success': False,
            'error': 'Invalid image path - must be within scanner folder'
        }), 400

    if not os.path.exists(image_path_abs):
        return jsonify({
            'success': False,
            'error': 'Image file not found'
        }), 404

    if not os.path.isfile(image_path_abs):
        return jsonify({
            'success': False,
            'error': 'Path is not a file'
        }), 400

    try:
        edited_path = apply_edits(image_path_abs, edits, output_path=image_path_abs)
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


@app.route('/apply_image_edits', methods=['POST'])
def apply_image_edits_endpoint():
    """Apply edits to an image."""
    global current_answer_copy
    
    if not current_answer_copy or not current_answer_copy.id:
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
            (img for img in current_answer_copy.images if img['sequence'] == sequence),
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


# PDF routes
@app.route('/list_pdfs', methods=['GET'])
def list_pdfs():
    """List all generated PDFs."""
    pdfs = list_pdfs_in_directory(config.output_dir)
    return jsonify({
        'pdfs': pdfs,
        'count': len(pdfs)
    })


@app.route('/cleanup_scanner_folder', methods=['POST'])
def cleanup_scanner_folder():
    """Delete all images from scanner folder."""
    result = cleanup_scanner_folder_internal()
    return jsonify({
        'success': True,
        **result
    })


# Auto image processing routes
@app.route('/auto_check_image', methods=['POST'])
def auto_check_image():
    """Auto check image for blur, cuts, borders, two pages, etc."""
    data = request.get_json()
    image_path = data.get('image_path')
    
    if not image_path:
        return jsonify({
            'success': False,
            'error': 'Image path is required'
        }), 400
    
    # Normalize the path - remove file:// prefix if present, normalize separators
    if image_path.startswith('file://'):
        image_path = image_path[7:]  # Remove 'file://' prefix
    # Normalize path separators for the current OS
    image_path = os.path.normpath(image_path)
    
    if not os.path.exists(image_path):
        return jsonify({
            'success': False,
            'error': f'Image file not found: {image_path}'
        }), 404
    
    if not os.path.isfile(image_path):
        return jsonify({
            'success': False,
            'error': f'Path is not a file: {image_path}'
        }), 400
    
    try:
        result = auto_processor.auto_process(image_path, auto_fix=False)
        # Debug print so backend console shows the "answer" (check results)
        try:
            print(
                f"🧾 [auto_check_image] {os.path.basename(image_path)} "
                f"needs_attention={bool(result.get('needs_attention'))} "
                f"warnings={len(result.get('warnings', []) or [])}"
                , flush=True
            )
            msgs = result.get('messages') or []
            if msgs:
                print("🧾 [auto_check_image] messages:", " | ".join(map(str, msgs)), flush=True)
        except Exception:
            pass
        return jsonify({
            'success': True,
            **result
        })
    except Exception as e:
        # Log the full traceback for debugging
        error_traceback = traceback.format_exc()
        logger.info(f"Error in auto_check_image: {error_traceback}", file=sys.stderr)
        return jsonify({
            'success': False,
            'error': f'Auto check failed: {str(e)}',
            'traceback': error_traceback if app.debug else None
        }), 500


@app.route('/auto_process_image', methods=['POST'])
def auto_process_image():
    """Auto process image with fixes (remove objects, crop borders, etc.)."""
    data = request.get_json()
    image_path = data.get('image_path')
    output_path = data.get('output_path')  # Optional
    
    if not image_path:
        return jsonify({
            'success': False,
            'error': 'Image path is required'
        }), 400
    
    # Normalize the path - remove file:// prefix if present, normalize separators
    if image_path.startswith('file://'):
        image_path = image_path[7:]  # Remove 'file://' prefix
    # Normalize path separators for the current OS
    image_path = os.path.normpath(image_path)
    
    if output_path:
        if output_path.startswith('file://'):
            output_path = output_path[7:]
        output_path = os.path.normpath(output_path)
    
    if not os.path.exists(image_path):
        return jsonify({
            'success': False,
            'error': f'Image file not found: {image_path}'
        }), 404
    
    if not os.path.isfile(image_path):
        return jsonify({
            'success': False,
            'error': f'Path is not a file: {image_path}'
        }), 400
    
    try:
        result = auto_processor.auto_process(image_path, output_path=output_path, auto_fix=True)
        deleted_original = False

        # Debug print so backend console shows the "answer" (full processing outcome)
        try:
            print(
                f"🧾 [auto_process_image] {os.path.basename(image_path)} "
                f"-> processed={os.path.basename(result.get('processed_image_path', '') or '')} "
                f"split_images={len(result.get('split_images', []) or [])} "
                f"fixes={result.get('fixes_applied', [])} "
                f"warnings={len(result.get('warnings', []) or [])} "
                f"needs_attention={bool(result.get('needs_attention'))}"
                , flush=True
            )
            msgs = result.get('messages') or []
            if msgs:
                print("🧾 [auto_process_image] messages:", " | ".join(map(str, msgs)), flush=True)
        except Exception:
            pass

        # If two pages were split, remove the original image
        split_images = result.get('split_images') or []
        if split_images:
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
                    deleted_original = True
            except Exception as delete_error:
                result.setdefault('warnings', []).append(
                    f"Could not delete original image after split: {delete_error}"
                )

        return jsonify({
            'success': True,
            'deleted_original': deleted_original,
            **result
        })
    except Exception as e:
        # Log the full traceback for debugging
        error_traceback = traceback.format_exc()
        print(f"Error in auto_process_image: {error_traceback}", file=sys.stderr)
        return jsonify({
            'success': False,
            'error': f'Auto processing failed: {str(e)}',
            'traceback': error_traceback if app.debug else None
        }), 500


@app.route('/split_two_pages', methods=['POST'])
def split_two_pages():
    """Split an image containing 2 pages into 2 separate images."""
    global current_answer_copy
    
    data = request.get_json()
    image_path = data.get('image_path')
    sequence = data.get('sequence')  # Optional: sequence number of image in current answer copy
    
    if not image_path:
        # Try to get from current answer copy if sequence is provided
        if sequence and current_answer_copy:
            image_data = next(
                (img for img in current_answer_copy.images if img['sequence'] == sequence),
                None
            )
            if image_data:
                image_path = image_data['path']
        
        if not image_path:
            return jsonify({
                'success': False,
                'error': 'Image path or sequence is required'
            }), 400
    
    if not os.path.exists(image_path):
        return jsonify({
            'success': False,
            'error': 'Image file not found'
        }), 404
    
    try:
        # Auto-rotate before split detection
        rotated_path, rotated = auto_processor.auto_rotate_image(image_path, output_path=image_path)
        if rotated:
            image_path = rotated_path

        # Detect if two pages
        two_pages_info = auto_processor.detect_two_pages(image_path)
        logger.info("two pages info",two_pages_info)
        if not two_pages_info.get('is_two_pages'):
            return jsonify({
                'success': False,
                'error': 'Two pages not detected in this image',
                'detection_info': two_pages_info
            }), 400
        
        # Determine output directory
        if current_answer_copy and sequence:
            output_dir = current_answer_copy.working_path
        else:
            output_dir = os.path.dirname(image_path)
        
        # Detect two pages first
        two_pages_info = auto_processor.detect_two_pages(image_path)

        if not two_pages_info.get('is_two_pages'):
            return jsonify({
                'success': False,
                'message': 'Single page detected. No split required.',
                'split_info': two_pages_info
            }), 200


        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Split the pages
        split_paths = auto_processor.split_two_pages(
            image_path=image_path,
            output_dir=output_dir,
            split_info=two_pages_info
        )
        logger.info("split paths",split_paths)
        if not split_paths:
            return jsonify({
                'success': False,
                'error': 'Page split failed'
            }), 500


        # Convert to relative paths / filenames for frontend
        split_files = [os.path.basename(p) for p in split_paths]

        return jsonify({
            'success': True,
            'split_images': split_files,
            'split_info': two_pages_info,
            'message': f'Split into {len(split_files)} pages'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Page splitting failed: {str(e)}'
        }), 500


@app.route('/split_image_with_crops', methods=['POST'])
def split_image_with_crops():
    """Split an image into two pages using manual crop boxes."""
    data = request.get_json()
    image_path = data.get('image_path')
    crops = data.get('crops', [])
    
    if not image_path or not isinstance(crops, list) or len(crops) != 2:
        return jsonify({
            'success': False,
            'error': 'Image path and 2 crop boxes are required'
        }), 400
    
    if image_path.startswith('file://'):
        image_path = image_path[7:]
    image_path = os.path.normpath(image_path)
    
    # Validate that the path is within the scanner directory for security
    scanner_dir_abs = os.path.abspath(config.scanner_watch_dir)
    image_path_abs = os.path.abspath(image_path)
    
    if not image_path_abs.startswith(scanner_dir_abs):
        return jsonify({
            'success': False,
            'error': 'Invalid image path - must be within scanner folder'
        }), 400
    
    if not os.path.exists(image_path_abs):
        return jsonify({
            'success': False,
            'error': 'Image file not found'
        }), 404
    
    try:
        img = Image.open(image_path_abs)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        width, height = img.size
        
        def clamp_crop(crop):
            x = int(crop.get('x', 0))
            y = int(crop.get('y', 0))
            w = int(crop.get('width', 0))
            h = int(crop.get('height', 0))
            
            x = max(0, min(x, width - 1))
            y = max(0, min(y, height - 1))
            w = max(1, min(w, width - x))
            h = max(1, min(h, height - y))
            return x, y, w, h
        
        output_dir = os.path.dirname(image_path_abs) or scanner_dir_abs
        base_name, ext = os.path.splitext(os.path.basename(image_path_abs))
        ext = ext if ext else '.jpg'
        
        output_paths = []
        for idx, crop in enumerate(crops, start=1):
            x, y, w, h = clamp_crop(crop)
            cropped = img.crop((x, y, x + w, y + h))
            output_path = os.path.join(output_dir, f"{base_name}_page{idx}{ext}")
            if ext.lower() in ['.jpg', '.jpeg']:
                cropped.save(output_path, quality=95, optimize=True)
            else:
                cropped.save(output_path)
            output_paths.append(output_path)
        
        try:
            if os.path.exists(image_path_abs):
                os.remove(image_path_abs)
        except Exception as delete_error:
            logger.warning(f"Could not delete original image after split: {delete_error}")
        
        return jsonify({
            'success': True,
            'split_images': output_paths,
            'message': 'Split into 2 pages'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Split failed: {str(e)}'
        }), 500


@app.route('/remove_yellow_objects', methods=['POST'])
def remove_yellow_objects_endpoint():
    """Remove yellow stickers/objects from image."""
    data = request.get_json()
    image_path = data.get('image_path')
    output_path = data.get('output_path')
    
    if not image_path:
        return jsonify({
            'success': False,
            'error': 'Image path is required'
        }), 400
    
    if not os.path.exists(image_path):
        return jsonify({
            'success': False,
            'error': 'Image file not found'
        }), 404
    
    try:
        processed_path = auto_processor.remove_yellow_objects(image_path, output_path)
        return jsonify({
            'success': True,
            'processed_image_path': processed_path,
            'message': 'Yellow objects removed'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to remove yellow objects: {str(e)}'
        }), 500


@app.route('/remove_fingers', methods=['POST'])
def remove_fingers_endpoint():
    """Remove finger marks from image."""
    data = request.get_json()
    image_path = data.get('image_path')
    output_path = data.get('output_path')
    
    if not image_path:
        return jsonify({
            'success': False,
            'error': 'Image path is required'
        }), 400
    
    if not os.path.exists(image_path):
        return jsonify({
            'success': False,
            'error': 'Image file not found'
        }), 404
    
    try:
        processed_path = auto_processor.remove_fingers(image_path, output_path)
        return jsonify({
            'success': True,
            'processed_image_path': processed_path,
            'message': 'Finger marks removed'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to remove fingers: {str(e)}'
        }), 500


# Exam details routes
@app.route('/set_exam_details', methods=['POST'])
def set_exam_details():
    """Set exam details for current answer copy."""
    global current_answer_copy
    
    if not current_answer_copy or not current_answer_copy.id:
        return jsonify({
            'success': False,
            'error': 'No active answer copy. Please start a new one first.'
        }), 400
    
    data = request.get_json()
    
    # Safely extract and strip values
    degree = safe_strip(data.get('degree'))
    subject = safe_strip(data.get('subject'))
    exam_date = safe_strip(data.get('exam_date'))
    college = safe_strip(data.get('college'))
    unique_id = safe_strip(data.get('unique_id'))
    
    # If unique_id is not provided, generate from fields
    if not unique_id:
        if degree and subject and exam_date and college:
            unique_id = generate_unique_id_from_fields(degree, subject, exam_date, college)
        # If still no unique_id and we have images, try to extract from first page
        if not unique_id and len(current_answer_copy.images) > 0:
            first_image_path = sorted(
                current_answer_copy.images,
                key=lambda x: x['sequence']
            )[0]['path']
            extracted_id = extract_unique_id_from_image(first_image_path)
            if extracted_id:
                unique_id = extracted_id
    
    # Update exam details
    current_answer_copy.exam_details = {
        'degree': degree,
        'subject': subject,
        'exam_date': exam_date,
        'college': college,
        'unique_id': unique_id
    }
    
    # Save exam details to settings
    config.save_settings(current_answer_copy.exam_details)
    
    return jsonify({
        'success': True,
        'message': 'Exam details saved',
        'exam_details': current_answer_copy.exam_details
    })


@app.route('/get_exam_details', methods=['GET'])
def get_exam_details():
    """Get exam details for current answer copy or from settings."""
    global current_answer_copy
    
    # If there's an active answer copy, return its exam details
    if current_answer_copy and current_answer_copy.id:
        return jsonify({
            'success': True,
            'exam_details': current_answer_copy.exam_details
        })
    
    # Otherwise, return exam details from saved settings (automatically loaded on startup)
    exam_details = config.get_saved_exam_details()
    
    return jsonify({
        'success': True,
        'exam_details': exam_details
    })


# Initialize on import
if __name__ == '__main__':
    # Create necessary directories
    os.makedirs(config.working_dir, exist_ok=True)
    os.makedirs(config.output_dir, exist_ok=True)
    os.makedirs(config.upload_dir, exist_ok=True)
    os.makedirs(config.scanner_watch_dir, exist_ok=True)
    
    # Start scanner watcher
    scanner_watcher.start()
    
    print(f"Starting Image Engine Server on http://127.0.0.1:{config.port}")
    try:
        app.run(host='127.0.0.1', port=config.port, debug=True)
    except KeyboardInterrupt:
        print("\nShutting down...")
        scanner_watcher.stop()
