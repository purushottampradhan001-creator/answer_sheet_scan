"""
Database initialization and management
"""

import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict


class Database:
    """Database manager for answer copies and images"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
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
    
    def create_answer_copy(self, answer_copy_id: str) -> bool:
        """Create a new answer copy record."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO answer_copies (id, created_at, image_count)
                VALUES (?, ?, ?)
            ''', (answer_copy_id, datetime.now(), 0))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error creating answer copy: {e}")
            return False
        finally:
            conn.close()
    
    def add_image(self, answer_copy_id: str, image_path: str, sequence_number: int) -> bool:
        """Add an image to an answer copy."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO images (answer_copy_id, image_path, sequence_number, uploaded_at)
                VALUES (?, ?, ?, ?)
            ''', (answer_copy_id, image_path, sequence_number, datetime.now()))
            
            cursor.execute('''
                UPDATE answer_copies
                SET image_count = ?
                WHERE id = ?
            ''', (sequence_number, answer_copy_id))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"Error adding image: {e}")
            return False
        finally:
            conn.close()
    
    def complete_answer_copy(self, answer_copy_id: str, pdf_path: str) -> bool:
        """Mark an answer copy as completed."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                UPDATE answer_copies
                SET completed_at = ?, pdf_path = ?
                WHERE id = ?
            ''', (datetime.now(), pdf_path, answer_copy_id))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error completing answer copy: {e}")
            return False
        finally:
            conn.close()
