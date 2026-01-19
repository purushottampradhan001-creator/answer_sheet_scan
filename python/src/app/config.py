"""
Application configuration management
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, Optional


def get_base_dir() -> str:
    """Get base directory for data files. Use writable location in production."""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle
        # Use user's home directory for data files
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
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Config:
    """Application configuration"""
    
    def __init__(self):
        self.base_dir = get_base_dir()
        self.working_dir = os.path.join(self.base_dir, 'working')
        self.output_dir = os.path.join(self.base_dir, 'output')
        self.db_path = os.path.join(self.base_dir, 'db', 'app.db')
        self.upload_dir = os.path.join(self.base_dir, 'uploads')
        self.scanner_watch_dir = os.path.join(self.base_dir, 'scanner_input')
        self.settings_file = os.path.join(self.base_dir, 'db', 'settings.json')
        self.port = 5001
        
        # Load settings from file
        self.load_settings()
    
    def load_settings(self):
        """Load settings from local JSON file."""
        default_settings = {
            'output_dir': self.output_dir,
            'scanner_watch_dir': self.scanner_watch_dir,
            'input_dir': self.scanner_watch_dir,
            'exam_details': {
                'degree': None,
                'subject': None,
                'exam_date': None,
                'college': None,
                'unique_id': None
            }
        }
        
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    
                    if 'output_dir' in settings:
                        try:
                            if not os.path.isdir(settings['output_dir']):
                                os.makedirs(settings['output_dir'], exist_ok=True)
                            self.output_dir = settings['output_dir']
                        except Exception as e:
                            print(f"⚠️  Could not use saved output_dir: {e}. Using default.")
                    
                    if 'scanner_watch_dir' in settings:
                        try:
                            if not os.path.isdir(settings['scanner_watch_dir']):
                                os.makedirs(settings['scanner_watch_dir'], exist_ok=True)
                            self.scanner_watch_dir = settings['scanner_watch_dir']
                        except Exception as e:
                            print(f"⚠️  Could not use saved scanner_watch_dir: {e}. Using default.")
                    
                    if 'input_dir' in settings and 'scanner_watch_dir' not in settings:
                        try:
                            if not os.path.isdir(settings['input_dir']):
                                os.makedirs(settings['input_dir'], exist_ok=True)
                            self.scanner_watch_dir = settings['input_dir']
                        except Exception as e:
                            print(f"⚠️  Could not use saved input_dir: {e}. Using default.")
                    
                    # Load and store exam_details from settings
                    if 'exam_details' in settings and isinstance(settings['exam_details'], dict):
                        self.saved_exam_details = settings['exam_details'].copy()
                    else:
                        self.saved_exam_details = {
                            'degree': None,
                            'subject': None,
                            'exam_date': None,
                            'college': None,
                            'unique_id': None
                        }
                    
                    print(f"✓ Settings loaded from {self.settings_file}")
                    print(f"  Output directory: {os.path.abspath(self.output_dir)}")
                    print(f"  Scanner folder: {os.path.abspath(self.scanner_watch_dir)}")
                    if self.saved_exam_details.get('degree') or self.saved_exam_details.get('subject'):
                        print(f"  Saved exam details: {self.saved_exam_details.get('degree')} - {self.saved_exam_details.get('subject')}")
            except Exception as e:
                print(f"⚠️  Error loading settings: {e}. Using defaults.")
                self.saved_exam_details = {
                    'degree': None,
                    'subject': None,
                    'exam_date': None,
                    'college': None,
                    'unique_id': None
                }
        else:
            # Create default settings file
            self.saved_exam_details = {
                'degree': None,
                'subject': None,
                'exam_date': None,
                'college': None,
                'unique_id': None
            }
            self.save_settings()
            print(f"✓ Created default settings file: {self.settings_file}")
    
    def get_saved_exam_details(self) -> Dict:
        """Get saved exam details from settings."""
        if hasattr(self, 'saved_exam_details'):
            return self.saved_exam_details.copy()
        # Fallback: try to load from file
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    return settings.get('exam_details', {
                        'degree': None,
                        'subject': None,
                        'exam_date': None,
                        'college': None,
                        'unique_id': None
                    })
            except:
                pass
        return {
            'degree': None,
            'subject': None,
            'exam_date': None,
            'college': None,
            'unique_id': None
        }
    
    def save_settings(self, exam_details: Optional[Dict] = None):
        """Save current settings to local JSON file."""
        try:
            os.makedirs(os.path.dirname(self.settings_file), exist_ok=True)
            # Use provided exam_details or load from file if available
            if exam_details is None:
                if os.path.exists(self.settings_file):
                    try:
                        with open(self.settings_file, 'r', encoding='utf-8') as f:
                            existing_settings = json.load(f)
                            exam_details = existing_settings.get('exam_details', {
                                'degree': None,
                                'subject': None,
                                'exam_date': None,
                                'college': None,
                                'unique_id': None
                            })
                    except:
                        exam_details = {
                            'degree': None,
                            'subject': None,
                            'exam_date': None,
                            'college': None,
                            'unique_id': None
                        }
                else:
                    exam_details = {
                        'degree': None,
                        'subject': None,
                        'exam_date': None,
                        'college': None,
                        'unique_id': None
                    }
            
            settings = {
                'output_dir': os.path.abspath(self.output_dir),
                'scanner_watch_dir': os.path.abspath(self.scanner_watch_dir),
                'input_dir': os.path.abspath(self.scanner_watch_dir),
                'exam_details': exam_details
            }
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2)
            print(f"✓ Settings saved to {self.settings_file}")
        except Exception as e:
            print(f"⚠️  Error saving settings: {e}")


# Global config instance
config = Config()
