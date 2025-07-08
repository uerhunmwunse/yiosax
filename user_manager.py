import sqlite3
from typing import List, Dict, Optional
import json
from datetime import datetime

class UserManager:
    def __init__(self, connection: sqlite3.Connection):
        self.conn = connection
        self._init_db()


    def _init_db(self):
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS trackings (
                user_id INTEGER,
                product_name TEXT,
                target_price REAL,
                sku TEXT,
                product_data TEXT,  -- Keep JSON data
                PRIMARY KEY (user_id, product_name))
        ''')
        self.conn.commit()

    def add_tracking(self, user_id: int, product_name: str,
                     target_price: float, sku: str, product_data: dict):
        self.conn.execute('''
            INSERT OR REPLACE INTO trackings
            VALUES (?, ?, ?, ?, ?)
        ''', (
            user_id,
            product_name,
            target_price,
            sku,
            json.dumps(product_data),
            # datetime.now().isoformat()  # Keep JSON storage
        ))
        self.conn.commit()

    def get_all_trackings(self) -> List[Dict]:
        """Get all tracked items for all users"""
        cursor = self.conn.execute('''
            SELECT user_id, product_name, target_price, sku, product_data
            FROM trackings
        ''')
        return [{
            'user_id': row[0],
            'product_name': row[1],
            'target_price': row[2],
            'sku': row[3],
            'product_data': json.loads(row[4])  # Convert JSON string to dict
        } for row in cursor.fetchall()]



    def remove_tracking(self, user_id: int, product_name: str) -> bool:
        cursor = self.conn.execute('''
            SELECT product_name FROM trackings WHERE user_id=?
        ''', (user_id,))
        rows = cursor.fetchall()

        matched_name = None
        for row in rows:
            saved_name = row[0].lower()
            if product_name.lower() in saved_name:
                matched_name = row[0]
                break

        if matched_name:
            self.conn.execute('''
                DELETE FROM trackings
                WHERE user_id=? AND product_name=?
            ''', (user_id, matched_name))
            self.conn.commit()
            return True

        return False

    def get_tracked_items(self, user_id: int) -> List[Dict]:
        cursor = self.conn.execute('''
            SELECT product_name, target_price, product_data
            FROM trackings
            WHERE user_id=?
        ''', (user_id,))

        return [{
            'name': row[0],
            'target_price': row[1],
            'data': json.loads(row[2])  # Convert JSON back to dict
        } for row in cursor.fetchall()]

    def remove_tracking_by_name(self, user_id: int, product_name: str):
        """Remove tracking by exact product name match"""
        self.conn.execute('''
            DELETE FROM trackings
            WHERE user_id=? AND product_name=?
        ''', (user_id, product_name))
        self.conn.commit()
        return self.conn.total_changes > 0

