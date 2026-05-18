import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import hashlib
import os
import datetime
import json
import threading
import time
import sys
from collections import defaultdict
IS_WINDOWS = sys.platform == 'win32'

if IS_WINDOWS:
    try:
        import keyboard
        import win32gui
        import win32con
        ANTI_CHEAT_AVAILABLE = True
    except ImportError:
        ANTI_CHEAT_AVAILABLE = False
        print("Warning: Anti-cheat features limited. Install keyboard and pywin32 for full features.")
else:
    ANTI_CHEAT_AVAILABLE = False
    print("Warning: Anti-cheat features are optimized for Windows.")

COLORS = {
    'primary': '#4361ee',
    'secondary': '#3f37c9',
    'success': '#4cc9f0',
    'danger': '#f72585',
    'warning': '#f8961e',
    'dark': '#1a1a2e',
    'light': '#f8f9fa',
    'gray': '#6c757d',
    'white': '#ffffff',
    'gradient_start': '#667eea',
    'gradient_end': '#764ba2'
}

# ── Security helpers ────────────────────────────────────────────────────────

_login_attempts: dict = defaultdict(list)  # {username: [timestamp, ...]}
_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 60


def hash_password(password: str, salt: bytes | None = None) -> tuple:
    """Return (hex_hash, hex_salt) using PBKDF2-HMAC-SHA256 with 260 000 iterations."""
    if salt is None:
        salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 260_000)
    return key.hex(), salt.hex()


def verify_password(password: str, stored_hash: str, salt_hex: str) -> bool:
    """Constant-time comparison of PBKDF2 hash."""
    salt = bytes.fromhex(salt_hex)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 260_000)
    return key.hex() == stored_hash


def check_login_rate_limit(username: str) -> tuple:
    """Return (allowed: bool, wait_seconds: int)."""
    now = time.time()
    attempts = [t for t in _login_attempts[username] if now - t < _LOCKOUT_SECONDS]
    _login_attempts[username] = attempts
    if len(attempts) >= _MAX_ATTEMPTS:
        wait = int(_LOCKOUT_SECONDS - (now - attempts[0]))
        return False, max(wait, 1)
    return True, 0


def record_failed_attempt(username: str) -> None:
    _login_attempts[username].append(time.time())


def validate_credentials_input(username: str, password: str) -> str | None:
    """Return an error message string or None if inputs are valid."""
    if not username or not password:
        return "Please enter username and password."
    if len(username) > 64:
        return "Username too long."
    if len(password) < 6:
        return "Password must be at least 6 characters."
    if len(password) > 128:
        return "Password too long."
    return None


class StyledButton(tk.Button):
    def __init__(self, master, text, command=None, **kwargs):
        super().__init__(master, text=text, command=command, **kwargs)
        self.configure(
            font=('Segoe UI', 11, 'bold'),
            relief=tk.FLAT,
            cursor='hand2',
            padx=20,
            pady=10
        )
        self.bind('<Enter>', self.on_enter)
        self.bind('<Leave>', self.on_leave)
    
    def on_enter(self, e):
        self.configure(bg=self.cget('bg').replace('30%', '20%') if '#4CAF50' in self.cget('bg') else self.cget('bg'))
    
    def on_leave(self, e):
        pass

class StyledEntry(tk.Entry):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.configure(
            font=('Segoe UI', 11),
            relief=tk.FLAT,
            bg=COLORS['white'],
            fg=COLORS['dark'],
            insertbackground=COLORS['primary']
        )
        self.bind('<FocusIn>', self.on_focus_in)
        self.bind('<FocusOut>', self.on_focus_out)
    
    def on_focus_in(self, e):
        self.configure(bg='#f0f0f0')
    
    def on_focus_out(self, e):
        self.configure(bg=COLORS['white'])

class GradientFrame(tk.Canvas):
    def __init__(self, parent, color1, color2, **kwargs):
        super().__init__(parent, **kwargs)
        self.color1 = color1
        self.color2 = color2
        self.bind('<Configure>', self.draw_gradient)
    
    def draw_gradient(self, event=None):
        self.delete('gradient')
        width = self.winfo_width()
        height = self.winfo_height()
        
        for i in range(height):
            ratio = i / height
            r = int(int(self.color1[1:3], 16) * (1 - ratio) + int(self.color2[1:3], 16) * ratio)
            g = int(int(self.color1[3:5], 16) * (1 - ratio) + int(self.color2[3:5], 16) * ratio)
            b = int(int(self.color1[5:7], 16) * (1 - ratio) + int(self.color2[5:7], 16) * ratio)
            color = f'#{r:02x}{g:02x}{b:02x}'
            self.create_line(0, i, width, i, fill=color, tags='gradient')
        
        self.lower('gradient')

class AntiCheatSystem:
    def __init__(self, exam_window, student_id, exam_id):
        self.exam_window = exam_window
        self.student_id = student_id
        self.exam_id = exam_id
        self.violations = []
        self.running = True
        
    def block_keys(self):
        """Block specific keys during exam (Windows only)"""
        if not IS_WINDOWS or not ANTI_CHEAT_AVAILABLE:
            return
            
        try:
            blocked_keys = ['alt', 'tab', 'esc', 'win', 'cmd']
            for key in blocked_keys:
                keyboard.block_key(key)
        except Exception as e:
            print(f"Warning: could not block key: {e}")
    
    def monitor_focus(self):
        """Monitor window focus changes"""
        if not IS_WINDOWS or not ANTI_CHEAT_AVAILABLE:
            return
            
        while self.running:
            try:
                import win32gui
                current_window = win32gui.GetForegroundWindow()
                
                try:
                    exam_handle = self.exam_window.winfo_id()
                except tk.TclError:
                    break
                
                if current_window != exam_handle:
                    violation = {
                        'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'type': 'Window Switch Attempt',
                        'details': "Tried to switch to another window"
                    }
                    self.violations.append(violation)
                    self.log_violation(violation)
                    
                    try:
                        win32gui.SetForegroundWindow(exam_handle)
                    except Exception:
                        pass
                        
            except Exception:
                pass
            
            time.sleep(0.5)
    
    def log_violation(self, violation):
        """Log violations to database"""
        try:
            conn = DatabaseManager.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO anti_cheat_logs 
                (student_id, exam_id, violation_type, violation_details, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (self.student_id, self.exam_id, violation['type'], 
                  violation['details'], violation['timestamp']))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Warning: could not log violation: {e}")
    
    def start_monitoring(self):
        """Start anti-cheat monitoring"""
        self.block_keys()
        if ANTI_CHEAT_AVAILABLE:
            monitor_thread = threading.Thread(target=self.monitor_focus, daemon=True)
            monitor_thread.start()
    
    def stop_monitoring(self):
        """Stop anti-cheat monitoring"""
        self.running = False
        if ANTI_CHEAT_AVAILABLE:
            try:
                keyboard.unhook_all()
            except Exception as e:
                print(f"Warning: could not unhook keyboard: {e}")

class DatabaseManager:
    @staticmethod
    def get_connection():
        return sqlite3.connect('exam_system.db')
    
    @staticmethod
    def initialize_database():
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                password_salt TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL,
                full_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Migration: add password_salt column to existing databases
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN password_salt TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # column already exists
        
        # Exams table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS exams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER,
                exam_name TEXT NOT NULL,
                subject TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL,
                total_marks INTEGER NOT NULL,
                exam_date TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                questions TEXT,
                FOREIGN KEY (teacher_id) REFERENCES users (id)
            )
        ''')
        
        # Exam results table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS exam_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                exam_id INTEGER,
                score INTEGER,
                total_marks INTEGER,
                answers TEXT,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES users (id),
                FOREIGN KEY (exam_id) REFERENCES exams (id)
            )
        ''')
        
        # Anti-cheat logs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS anti_cheat_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                exam_id INTEGER,
                violation_type TEXT,
                violation_details TEXT,
                timestamp TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES users (id),
                FOREIGN KEY (exam_id) REFERENCES exams (id)
            )
        ''')
        
        # Create default accounts (for demo only – change passwords in production)
        # Teacher accounts
        try:
            teacher_accounts = [
                ('tcr111', 'demo123', 'Demo Teacher'),
                ('tcr112', 'sakurahismail', 'Sakurah Ismail'),
                ('tcr113', 'rifazumana', 'Rifa Zumana')
            ]
            for uname, pwd, fname in teacher_accounts:
                hashed_pw, pw_salt = hash_password(pwd)
                cursor.execute('''
                    INSERT OR IGNORE INTO users (username, password, password_salt, role, full_name)
                    VALUES (?, ?, ?, ?, ?)
                ''', (uname, hashed_pw, pw_salt, 'teacher', fname))
        except Exception as e:
            print(f"Warning: could not create default teacher accounts: {e}")
        
        try:
            student_accounts = [
                ('rzb' or '0712340012101011', '101011', 'Md. Razab Ali'),
                ('sakib' or '0712340012101028', '101028', 'Sakubul Hasan'),
                ('sanjida' or '0712340012101037', '101037', 'Sanjida Emros'),
                ('polash' or '0712340012101045', '101045', 'Polash Ali'),
                ('raja' or '0712340012101046', '101046', 'Raja Hossein')
            ]
            for uname, pwd, fname in student_accounts:
                hashed_pw, pw_salt = hash_password(pwd)
                cursor.execute('''
                    INSERT OR IGNORE INTO users (username, password, password_salt, role, full_name)
                    VALUES (?, ?, ?, ?, ?)
                ''', (uname, hashed_pw, pw_salt, 'student', fname))
        except Exception as e:
            print(f"Warning: could not create default student accounts: {e}")
        
        cursor.execute('SELECT COUNT(*) FROM exams')
        exam_count = cursor.fetchone()[0]
        
        if exam_count == 0:
            cursor.execute('SELECT id FROM users WHERE username="tcr111"')
            teacher_row = cursor.fetchone()
            if teacher_row:
                teacher_id = teacher_row[0]
            else:
                # Fallback: create a default teacher if none exists
                hashed_pw, pw_salt = hash_password('demo123')
                cursor.execute('''
                    INSERT INTO users (username, password, password_salt, role, full_name)
                    VALUES (?, ?, ?, ?, ?)
                ''', ('tcr111', hashed_pw, pw_salt, 'teacher', 'Demo Teacher'))
                conn.commit()
                cursor.execute('SELECT id FROM users WHERE username="tcr111"')
                teacher_id = cursor.fetchone()[0]
            
            exam1_questions = [
                {
                    'text': 'What is the correct way to create a function in Python?',
                    'options': ['function myFunction():', 'def myFunction():', 'create myFunction():', 'new myFunction():'],
                    'correct': 'B',
                    'marks': 5
                },
                {
                    'text': 'Which of the following is used to get user input in Python?',
                    'options': ['input()', 'get()', 'scan()', 'read()'],
                    'correct': 'A',
                    'marks': 5
                },
                {
                    'text': 'What does "PEP" stand for in Python?',
                    'options': ['Python Enhancement Proposal', 'Python Executive Protocol', 'Python Essential Package', 'Python Evaluation Process'],
                    'correct': 'A',
                    'marks': 5
                },
                {
                    'text': 'Which of the following is a correct way to comment in Python?',
                    'options': ['// This is a comment', '<!-- This is a comment -->', '# This is a comment', '/* This is a comment */'],
                    'correct': 'C',
                    'marks': 5
                },
                {
                    'text': 'What is the output of print(2**3)?',
                    'options': ['6', '8', '9', '5'],
                    'correct': 'B',
                    'marks': 5
                }
            ]
            
            cursor.execute('''
                INSERT INTO exams (teacher_id, exam_name, subject, duration_minutes, total_marks, exam_date, questions, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (teacher_id, 'Python Programming Basics', 'Programming', 30, 25, 
                  (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M"),
                  json.dumps(exam1_questions), 'pending'))
            
            exam2_questions = [
                {
                    'text': 'What is the square root of 144?',
                    'options': ['10', '11', '12', '13'],
                    'correct': 'C',
                    'marks': 5
                },
                {
                    'text': 'What is 15% of 200?',
                    'options': ['20', '25', '30', '35'],
                    'correct': 'C',
                    'marks': 5
                },
                {
                    'text': 'If x + 5 = 12, what is the value of x?',
                    'options': ['5', '6', '7', '8'],
                    'correct': 'C',
                    'marks': 5
                },
                {
                    'text': 'What is the area of a circle with radius 3? (Use π = 3.14)',
                    'options': ['28.26', '28.26', '18.84', '9.42'],
                    'correct': 'A',
                    'marks': 5
                },
                {
                    'text': 'What is the value of 5! (5 factorial)?',
                    'options': ['60', '120', '24', '720'],
                    'correct': 'B',
                    'marks': 5
                }
            ]
            
            cursor.execute('''
                INSERT INTO exams (teacher_id, exam_name, subject, duration_minutes, total_marks, exam_date, questions, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (teacher_id, 'Mathematics Fundamentals', 'Mathematics', 45, 25, 
                  (datetime.datetime.now() + datetime.timedelta(days=2)).strftime("%Y-%m-%d %H:%M"),
                  json.dumps(exam2_questions), 'pending'))
            
            exam3_questions = [
                {
                    'text': 'Who wrote "Romeo and Juliet"?',
                    'options': ['Charles Dickens', 'William Shakespeare', 'Jane Austen', 'Mark Twain'],
                    'correct': 'B',
                    'marks': 5
                },
                {
                    'text': 'What is the capital of France?',
                    'options': ['London', 'Berlin', 'Paris', 'Madrid'],
                    'correct': 'C',
                    'marks': 5
                },
                {
                    'text': 'Which planet is known as the Red Planet?',
                    'options': ['Mars', 'Jupiter', 'Venus', 'Saturn'],
                    'correct': 'A',
                    'marks': 5
                },
                {
                    'text': 'Who painted the Mona Lisa?',
                    'options': ['Van Gogh', 'Picasso', 'Da Vinci', 'Rembrandt'],
                    'correct': 'C',
                    'marks': 5
                },
                {
                    'text': 'What is the largest ocean on Earth?',
                    'options': ['Atlantic Ocean', 'Indian Ocean', 'Arctic Ocean', 'Pacific Ocean'],
                    'correct': 'D',
                    'marks': 5
                }
            ]
            
            cursor.execute('''
                INSERT INTO exams (teacher_id, exam_name, subject, duration_minutes, total_marks, exam_date, questions, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (teacher_id, 'General Knowledge Quiz', 'General Knowledge', 20, 25, 
                  (datetime.datetime.now() + datetime.timedelta(days=3)).strftime("%Y-%m-%d %H:%M"),
                  json.dumps(exam3_questions), 'pending'))
        
        conn.commit()
        conn.close()

class ModernButton(tk.Button):
    def __init__(self, master, text, command=None, color=COLORS['primary'], **kwargs):
        super().__init__(master, text=text, command=command, **kwargs)
        self.configure(
            font=('Segoe UI', 12, 'bold'),
            bg=color,
            fg='white',
            relief=tk.FLAT,
            cursor='hand2',
            padx=30,
            pady=12,
            bd=0
        )
        self.bind('<Enter>', self.on_enter)
        self.bind('<Leave>', self.on_leave)
    
    def on_enter(self, e):
        self.configure(bg=COLORS['secondary'])
    
    def on_leave(self, e):
        self.configure(bg=COLORS['primary'])

class RoleSelectionWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("Online Exam Simulator with Anti-Cheat System")
        self.root.geometry("760x520")
        self.root.configure(bg=COLORS['light'])
        self.root.resizable(False, False)
        self.center_window()

        # ── Main container ───────────────────────────────────────────────
        main = tk.Frame(self.root, bg=COLORS['light'])
        main.pack(fill=tk.BOTH, expand=True)

        # Accent top bar
        tk.Frame(main, bg=COLORS['primary'], height=6).pack(fill=tk.X)

        # ── Header card ────────────────────────────────────────────────
        header = tk.Frame(main, bg=COLORS['white'], pady=28)
        header.pack(fill=tk.X, padx=24, pady=(22, 0))

        tk.Label(header, text="📚 Online Exam System",
                 font=('Segoe UI', 30, 'bold'),
                 bg=COLORS['white'], fg=COLORS['dark']).pack()
        tk.Label(header, text="Secure  •  Reliable  •  Efficient",
                 font=('Segoe UI', 12), bg=COLORS['white'],
                 fg=COLORS['gray']).pack(pady=(4, 0))

        # ── Content card ─────────────────────────────────────────────────
        card = tk.Frame(main, bg=COLORS['white'], padx=50, pady=36,
                        relief=tk.FLAT, bd=0,
                        highlightbackground='#e0e0e0', highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True, padx=24, pady=18)

        tk.Label(card, text="Welcome!", font=('Segoe UI', 22, 'bold'),
                 bg=COLORS['white'], fg=COLORS['primary']).pack(pady=(0, 6))
        tk.Label(card, text="Please select your role to continue",
                 font=('Segoe UI', 11), bg=COLORS['white'],
                 fg=COLORS['gray']).pack(pady=(0, 28))

        # ── Role buttons row ─────────────────────────────────────────────
        row = tk.Frame(card, bg=COLORS['white'])
        row.pack()

        # Student button
        student_btn = tk.Button(
            row, text="👨‍🎓  Student Portal",
            font=('Segoe UI', 13, 'bold'),
            bg=COLORS['primary'], fg='white',
            width=18, height=2,
            relief=tk.FLAT, cursor='hand2',
            command=self.open_student_login)
        student_btn.pack(side='left', padx=(0, 10))
        student_btn.bind('<Enter>', lambda e: student_btn.configure(bg=COLORS['secondary']))
        student_btn.bind('<Leave>', lambda e: student_btn.configure(bg=COLORS['primary']))

        # "or" separator
        sep_frame = tk.Frame(row, bg=COLORS['white'], width=60)
        sep_frame.pack(side='left', padx=6)
        sep_frame.pack_propagate(False)
        tk.Label(sep_frame, text="or", font=('Segoe UI', 13, 'italic'),
                 bg=COLORS['white'], fg=COLORS['gray']).place(relx=0.5, rely=0.5, anchor='center')

        # Teacher button
        teacher_btn = tk.Button(
            row, text="👨‍🏫  Teacher Portal",
            font=('Segoe UI', 13, 'bold'),
            bg=COLORS['success'], fg='white',
            width=18, height=2,
            relief=tk.FLAT, cursor='hand2',
            command=self.open_teacher_login)
        teacher_btn.pack(side='left', padx=(10, 0))
        teacher_btn.bind('<Enter>', lambda e: teacher_btn.configure(bg='#3aa8c5'))
        teacher_btn.bind('<Leave>', lambda e: teacher_btn.configure(bg=COLORS['success']))

        # Exit button
        exit_btn = tk.Button(card, text="✕  Exit",
                             font=('Segoe UI', 10), bg=COLORS['danger'], fg='white',
                             width=12, relief=tk.FLAT, cursor='hand2',
                             command=self.root.quit)
        exit_btn.pack(pady=(28, 0))
        exit_btn.bind('<Enter>', lambda e: exit_btn.configure(bg='#d91a6c'))
        exit_btn.bind('<Leave>', lambda e: exit_btn.configure(bg=COLORS['danger']))

        # ── Footer ───────────────────────────────────────────────────────
        tk.Frame(main, bg='#e0e0e0', height=1).pack(fill=tk.X, side=tk.BOTTOM)
        tk.Label(main, text="© 2026 Online Exam System  |  All Rights Reserved by Team DQ",
                 font=('Segoe UI', 8), bg=COLORS['light'],
                 fg=COLORS['gray']).pack(side=tk.BOTTOM, pady=8)
    
    def center_window(self):
        self.root.update_idletasks()
        w, h = 760, 520
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f'{w}x{h}+{x}+{y}')
    
    def open_student_login(self):
        self.root.destroy()
        student_login_root = tk.Tk()
        StudentLoginWindow(student_login_root)
        student_login_root.mainloop()
    
    def open_teacher_login(self):
        self.root.destroy()
        teacher_login_root = tk.Tk()
        TeacherLoginWindow(teacher_login_root)
        teacher_login_root.mainloop()

class StudentLoginWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("Student Login - Online Exam System")
        self.root.configure(bg=COLORS['light'])
        self.root.resizable(False, False)
        self.center_window()

        main_container = tk.Frame(self.root, bg=COLORS['light'])
        main_container.pack(fill=tk.BOTH, expand=True)

        # Accent top bar
        tk.Frame(main_container, bg=COLORS['primary'], height=5).pack(fill=tk.X)

        # Back button row
        back_row = tk.Frame(main_container, bg=COLORS['light'])
        back_row.pack(fill=tk.X, padx=20, pady=(12, 0))
        back_btn = tk.Button(back_row, text="← Back", font=('Segoe UI', 10),
                             bg=COLORS['gray'], fg='white', relief=tk.FLAT,
                             cursor='hand2', padx=10, pady=4, command=self.go_back)
        back_btn.pack(anchor='w')
        back_btn.bind('<Enter>', lambda e: back_btn.configure(bg='#5a6268'))
        back_btn.bind('<Leave>', lambda e: back_btn.configure(bg=COLORS['gray']))

        # Login card
        login_card = tk.Frame(main_container, bg=COLORS['white'],
                              padx=35, pady=25,
                              highlightbackground='#ddd', highlightthickness=1)
        login_card.pack(fill=tk.BOTH, expand=True, padx=30, pady=14)

        # Icon
        tk.Label(login_card, text="👨‍🎓", font=('Segoe UI', 42),
                 bg=COLORS['white'], fg=COLORS['primary']).pack(pady=(0, 6))

        # Title & subtitle
        tk.Label(login_card, text="Student Login",
                 font=('Segoe UI', 22, 'bold'),
                 bg=COLORS['white'], fg=COLORS['dark']).pack()
        tk.Label(login_card, text="Access your exams and results",
                 font=('Segoe UI', 10), bg=COLORS['white'],
                 fg=COLORS['gray']).pack(pady=(2, 16))

        # Username
        u_frame = tk.Frame(login_card, bg=COLORS['white'])
        u_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(u_frame, text="Username", font=('Segoe UI', 11, 'bold'),
                 bg=COLORS['white'], fg=COLORS['dark']).pack(anchor='w')
        self.username_entry = tk.Entry(u_frame, font=('Segoe UI', 12),
                                       bg='#f8f9fa', fg=COLORS['dark'],
                                       relief=tk.FLAT, highlightthickness=1,
                                       highlightcolor=COLORS['primary'],
                                       highlightbackground='#ddd')
        self.username_entry.pack(fill=tk.X, pady=(4, 0), ipady=7)

        # Password
        p_frame = tk.Frame(login_card, bg=COLORS['white'])
        p_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(p_frame, text="Password", font=('Segoe UI', 11, 'bold'),
                 bg=COLORS['white'], fg=COLORS['dark']).pack(anchor='w')
        pw_row = tk.Frame(p_frame, bg=COLORS['white'])
        pw_row.pack(fill=tk.X, pady=(4, 0))
        self.password_entry = tk.Entry(pw_row, font=('Segoe UI', 12),
                                       bg='#f8f9fa', fg=COLORS['dark'],
                                       relief=tk.FLAT, highlightthickness=1,
                                       highlightcolor=COLORS['primary'],
                                       highlightbackground='#ddd', show='•')
        self.password_entry.pack(side='left', fill=tk.X, expand=True, ipady=7)

        def toggle_pw():
            if self.password_entry.cget('show') == '•':
                self.password_entry.config(show='')
                show_btn.config(text='🙈')
            else:
                self.password_entry.config(show='•')
                show_btn.config(text='👁')

        show_btn = tk.Button(pw_row, text='👁', font=('Segoe UI', 11),
                             bg='#f8f9fa', relief=tk.FLAT, cursor='hand2',
                             command=toggle_pw, bd=0, padx=6)
        show_btn.pack(side='left')

        # Login button
        login_btn = tk.Button(login_card, text="Login →",
                              font=('Segoe UI', 12, 'bold'),
                              bg=COLORS['primary'], fg='white',
                              relief=tk.FLAT, cursor='hand2',
                              command=self.login)
        login_btn.pack(fill=tk.X, pady=(18, 0), ipady=9)
        login_btn.bind('<Enter>', lambda e: login_btn.configure(bg=COLORS['secondary']))
        login_btn.bind('<Leave>', lambda e: login_btn.configure(bg=COLORS['primary']))

        self.username_entry.bind('<Return>', lambda e: self.login())
        self.password_entry.bind('<Return>', lambda e: self.login())
        self.username_entry.focus_set()

        # Footer
        tk.Label(main_container,
                 text="🔒 Secure Login  •  Protected by Anti-Cheat System",
                 font=('Segoe UI', 8), bg=COLORS['light'],
                 fg=COLORS['gray']).pack(side=tk.BOTTOM, pady=8)
    
    def center_window(self):
        self.root.update_idletasks()
        w, h = 500, 580
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f'{w}x{h}+{x}+{y}')
    
    def go_back(self):
        self.root.destroy()
        root = tk.Tk()
        RoleSelectionWindow(root)
        root.mainloop()
    
    def login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get()

        err = validate_credentials_input(username, password)
        if err:
            messagebox.showerror("Error", err)
            return

        allowed, wait = check_login_rate_limit(username)
        if not allowed:
            messagebox.showerror("Too Many Attempts",
                                 f"Account temporarily locked. Try again in {wait} seconds.")
            return

        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, username, role, full_name, password, password_salt '
            'FROM users WHERE username=? AND role="student"',
            (username,))
        row = cursor.fetchone()

        authenticated = False
        if row:
            if row[5]:  # PBKDF2 path
                authenticated = verify_password(password, row[4], row[5])
            else:        # Legacy SHA-256 — upgrade on success
                import hashlib as _hl
                legacy_hash = _hl.sha256(password.encode()).hexdigest()
                if legacy_hash == row[4]:
                    authenticated = True
                    new_hash, new_salt = hash_password(password)
                    cursor.execute(
                        'UPDATE users SET password=?, password_salt=? WHERE id=?',
                        (new_hash, new_salt, row[0]))
                    conn.commit()
        conn.close()

        if authenticated:
            self.root.destroy()
            StudentDashboard(row[:4])
        else:
            record_failed_attempt(username)
            messagebox.showerror("Error", "Invalid username or password.")

class TeacherLoginWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("Teacher Login - Online Exam System")
        self.root.configure(bg=COLORS['light'])
        self.root.resizable(False, False)
        self.center_window()

        main_container = tk.Frame(self.root, bg=COLORS['light'])
        main_container.pack(fill=tk.BOTH, expand=True)

        # Accent top bar
        tk.Frame(main_container, bg=COLORS['success'], height=5).pack(fill=tk.X)

        # Back button row
        back_row = tk.Frame(main_container, bg=COLORS['light'])
        back_row.pack(fill=tk.X, padx=20, pady=(12, 0))
        back_btn = tk.Button(back_row, text="← Back", font=('Segoe UI', 10),
                             bg=COLORS['gray'], fg='white', relief=tk.FLAT,
                             cursor='hand2', padx=10, pady=4, command=self.go_back)
        back_btn.pack(anchor='w')
        back_btn.bind('<Enter>', lambda e: back_btn.configure(bg='#5a6268'))
        back_btn.bind('<Leave>', lambda e: back_btn.configure(bg=COLORS['gray']))

        # Login card
        login_card = tk.Frame(main_container, bg=COLORS['white'],
                              padx=35, pady=25,
                              highlightbackground='#ddd', highlightthickness=1)
        login_card.pack(fill=tk.BOTH, expand=True, padx=30, pady=14)

        # Icon
        tk.Label(login_card, text="👨‍🏫", font=('Segoe UI', 42),
                 bg=COLORS['white'], fg=COLORS['success']).pack(pady=(0, 6))

        # Title & subtitle
        tk.Label(login_card, text="Teacher Login",
                 font=('Segoe UI', 22, 'bold'),
                 bg=COLORS['white'], fg=COLORS['dark']).pack()
        tk.Label(login_card, text="Manage exams and view results",
                 font=('Segoe UI', 10), bg=COLORS['white'],
                 fg=COLORS['gray']).pack(pady=(2, 16))

        # Username
        u_frame = tk.Frame(login_card, bg=COLORS['white'])
        u_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(u_frame, text="Username", font=('Segoe UI', 11, 'bold'),
                 bg=COLORS['white'], fg=COLORS['dark']).pack(anchor='w')
        self.username_entry = tk.Entry(u_frame, font=('Segoe UI', 12),
                                       bg='#f8f9fa', fg=COLORS['dark'],
                                       relief=tk.FLAT, highlightthickness=1,
                                       highlightcolor=COLORS['success'],
                                       highlightbackground='#ddd')
        self.username_entry.pack(fill=tk.X, pady=(4, 0), ipady=7)

        # Password
        p_frame = tk.Frame(login_card, bg=COLORS['white'])
        p_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(p_frame, text="Password", font=('Segoe UI', 11, 'bold'),
                 bg=COLORS['white'], fg=COLORS['dark']).pack(anchor='w')
        pw_row = tk.Frame(p_frame, bg=COLORS['white'])
        pw_row.pack(fill=tk.X, pady=(4, 0))
        self.password_entry = tk.Entry(pw_row, font=('Segoe UI', 12),
                                       bg='#f8f9fa', fg=COLORS['dark'],
                                       relief=tk.FLAT, highlightthickness=1,
                                       highlightcolor=COLORS['success'],
                                       highlightbackground='#ddd', show='•')
        self.password_entry.pack(side='left', fill=tk.X, expand=True, ipady=7)

        def toggle_pw_t():
            if self.password_entry.cget('show') == '•':
                self.password_entry.config(show='')
                show_btn_t.config(text='🙈')
            else:
                self.password_entry.config(show='•')
                show_btn_t.config(text='👁')

        show_btn_t = tk.Button(pw_row, text='👁', font=('Segoe UI', 11),
                               bg='#f8f9fa', relief=tk.FLAT, cursor='hand2',
                               command=toggle_pw_t, bd=0, padx=6)
        show_btn_t.pack(side='left')

        # Login button
        login_btn = tk.Button(login_card, text="Login →",
                              font=('Segoe UI', 12, 'bold'),
                              bg=COLORS['success'], fg='white',
                              relief=tk.FLAT, cursor='hand2',
                              command=self.login)
        login_btn.pack(fill=tk.X, pady=(18, 0), ipady=9)
        login_btn.bind('<Enter>', lambda e: login_btn.configure(bg='#3aa8c5'))
        login_btn.bind('<Leave>', lambda e: login_btn.configure(bg=COLORS['success']))

        self.username_entry.bind('<Return>', lambda e: self.login())
        self.password_entry.bind('<Return>', lambda e: self.login())
        self.username_entry.focus_set()

        # Footer
        tk.Label(main_container,
                 text="🔒 Secure Login  •  Protected by Anti-Cheat System",
                 font=('Segoe UI', 8), bg=COLORS['light'],
                 fg=COLORS['gray']).pack(side=tk.BOTTOM, pady=8)
    
    def center_window(self):
        self.root.update_idletasks()
        w, h = 500, 580
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f'{w}x{h}+{x}+{y}')
    
    def go_back(self):
        self.root.destroy()
        root = tk.Tk()
        RoleSelectionWindow(root)
        root.mainloop()
    
    def login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get()

        err = validate_credentials_input(username, password)
        if err:
            messagebox.showerror("Error", err)
            return

        allowed, wait = check_login_rate_limit(username)
        if not allowed:
            messagebox.showerror("Too Many Attempts",
                                 f"Account temporarily locked. Try again in {wait} seconds.")
            return

        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, username, role, full_name, password, password_salt '
            'FROM users WHERE username=? AND role="teacher"',
            (username,))
        row = cursor.fetchone()

        authenticated = False
        if row:
            if row[5]:  # PBKDF2 path (salt present)
                authenticated = verify_password(password, row[4], row[5])
            else:        # Legacy SHA-256 path — upgrade on success
                import hashlib as _hl
                legacy_hash = _hl.sha256(password.encode()).hexdigest()
                if legacy_hash == row[4]:
                    authenticated = True
                    # Upgrade to PBKDF2
                    new_hash, new_salt = hash_password(password)
                    cursor.execute(
                        'UPDATE users SET password=?, password_salt=? WHERE id=?',
                        (new_hash, new_salt, row[0]))
                    conn.commit()
        conn.close()

        if authenticated:
            self.root.destroy()
            TeacherDashboard(row[:4])
        else:
            record_failed_attempt(username)
            messagebox.showerror("Error", "Invalid username or password.")

class TeacherDashboard:
    def __init__(self, user):
        self.user = user
        self.root = tk.Tk()
        self.root.title(f"Teacher Dashboard - {user[3]}")
        self.root.geometry("1400x800")
        self.root.configure(bg=COLORS['light'])
        
        # Create menu bar
        menubar = tk.Menu(self.root, bg=COLORS['white'], fg=COLORS['dark'])
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0, bg=COLORS['white'], fg=COLORS['dark'])
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Logout", command=self.logout)
        file_menu.add_command(label="Exit", command=self.root.quit)
        
        header_frame = tk.Frame(self.root, bg=COLORS['primary'], height=80)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)

        # ── RIGHT: Logout button (packed first — side='right' must come before side='left')
        logout_btn = tk.Button(header_frame, text="Logout",
                               font=('Segoe UI', 11, 'bold'),
                               bg=COLORS['danger'], fg='white',
                               relief=tk.FLAT, cursor='hand2',
                               padx=14, pady=6,
                               command=self.logout)
        logout_btn.pack(side='right', padx=20, pady=20)
        logout_btn.bind('<Enter>', lambda e: logout_btn.configure(bg='#b01050'))
        logout_btn.bind('<Leave>', lambda e: logout_btn.configure(bg=COLORS['danger']))

        # ── LEFT: Welcome + name ─────────────────────────────────────────
        welcome_frame = tk.Frame(header_frame, bg=COLORS['primary'])
        welcome_frame.pack(side='left', padx=30, pady=14)
        tk.Label(welcome_frame, text="Welcome back,",
                 font=('Segoe UI', 11), bg=COLORS['primary'], fg='#d0e8ff').pack(anchor='w')
        tk.Label(welcome_frame, text=str(user[3]),
                 font=('Segoe UI', 18, 'bold'), bg=COLORS['primary'], fg='white').pack(anchor='w')

        # ── CENTER: Dashboard title ──────────────────────────────────────
        tk.Label(header_frame, text="Teacher Dashboard",
                 font=('Segoe UI', 18, 'bold'), bg=COLORS['primary'], fg='white').place(
                 relx=0.5, rely=0.5, anchor='center')

        # ── Stats cards (clickable) ──────────────────────────────────────
        stats_frame = tk.Frame(self.root, bg=COLORS['light'], height=120)
        stats_frame.pack(fill='x', padx=20, pady=20)
        stats_frame.pack_propagate(False)

        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM exams WHERE teacher_id=?', (self.user[0],))
        total_exams = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM exam_results WHERE exam_id IN (SELECT id FROM exams WHERE teacher_id=?)', (self.user[0],))
        total_submissions = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM anti_cheat_logs WHERE exam_id IN (SELECT id FROM exams WHERE teacher_id=?)', (self.user[0],))
        total_violations = cursor.fetchone()[0]
        conn.close()

        stats = [
            ('📝 Total Exams',       total_exams,       COLORS['primary'], self.view_exams),
            ('📊 Total Submissions', total_submissions,  COLORS['success'], self.view_results),
            ('⚠️ Violations',        total_violations,   COLORS['danger'],  self.view_logs),
        ]

        for i, (title, value, color, action) in enumerate(stats):
            card = tk.Frame(stats_frame, bg='white', relief=tk.FLAT, bd=0,
                            cursor='hand2',
                            highlightbackground='#e0e0e0', highlightthickness=1)
            card.place(x=i * 260 + 20, y=10, width=235, height=90)

            title_lbl = tk.Label(card, text=title, font=('Segoe UI', 10),
                                 bg='white', fg=COLORS['gray'], cursor='hand2')
            title_lbl.place(x=15, y=10)

            val_lbl = tk.Label(card, text=str(value), font=('Segoe UI', 26, 'bold'),
                               bg='white', fg=color, cursor='hand2')
            val_lbl.place(x=15, y=35)

            hint_lbl = tk.Label(card, font=('Segoe UI', 8, 'italic'),
                                bg='white', fg='#aaaaaa', cursor='hand2')
            hint_lbl.place(x=15, y=68)

            # Hover + click for card and all child labels
            def _on_enter(e, c=card, clr=color):
                c.configure(highlightbackground=clr, highlightthickness=2)
            def _on_leave(e, c=card):
                c.configure(highlightbackground='#e0e0e0', highlightthickness=1)

            for widget in (card, title_lbl, val_lbl, hint_lbl):
                widget.bind('<Button-1>', lambda e, fn=action: fn())
                widget.bind('<Enter>', _on_enter)
                widget.bind('<Leave>', _on_leave)
        
        # Main content frame
        self.main_frame = tk.Frame(self.root, bg=COLORS['light'])
        self.main_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        # Navigation buttons with modern styling
        nav_frame = tk.Frame(self.main_frame, bg=COLORS['light'])
        nav_frame.pack(fill='x', pady=(0, 20))
        
        buttons = [
            ('📝 Create New Exam', self.create_exam, COLORS['primary']),
            ('📋 View My Exams', self.view_exams, COLORS['success']),
            ('📊 View Results', self.view_results, COLORS['warning']),
            ('🔒 Anti-Cheat Logs', self.view_logs, COLORS['danger'])
        ]
        
        for text, command, color in buttons:
            btn = tk.Button(nav_frame, text=text, font=('Segoe UI', 11, 'bold'),
                           bg=color, fg='white', relief=tk.FLAT, cursor='hand2',
                           padx=20, pady=10, command=command)
            btn.pack(side='left', padx=5)
            btn.bind('<Enter>', lambda e, c=color: e.widget.configure(bg=self.darken_color(c)))
            btn.bind('<Leave>', lambda e, c=color: e.widget.configure(bg=c))
        
        self.content_frame = tk.Frame(self.main_frame, bg='white', relief=tk.FLAT, bd=0)
        self.content_frame.pack(fill='both', expand=True)
        
        self.content_frame.configure(highlightbackground=COLORS['gray'], highlightthickness=1)
        
        self.show_welcome()
        
        self.root.mainloop()
    
    def darken_color(self, color):
        """Darken a color for hover effect"""
        return COLORS['secondary'] if color == COLORS['primary'] else \
               '#3aa8c5' if color == COLORS['success'] else \
               '#e07a1a' if color == COLORS['warning'] else \
               '#d91a6c'
    
    def show_welcome(self):
        self.clear_content()
        welcome_frame = tk.Frame(self.content_frame, bg='white')
        welcome_frame.pack(expand=True, fill='both', padx=50, pady=50)
        
        icon_label = tk.Label(welcome_frame, text="👋", font=('Segoe UI', 64),
                             bg='white', fg=COLORS['primary'])
        icon_label.pack(pady=(0, 20))
        
        welcome_text = f"Welcome to Teacher Dashboard, {self.user[3]}!"
        tk.Label(welcome_frame, text=welcome_text, font=('Segoe UI', 20, 'bold'), 
                bg='white', fg=COLORS['dark']).pack(pady=10)
        
        features = [
            "• Create new exams with custom questions",
            "• Manage and view all your exams",
            "• Check student results and performance",
            "• Monitor anti-cheat violation logs"
        ]
        
        for feature in features:
            tk.Label(welcome_frame, text=feature, font=('Segoe UI', 11), 
                    bg='white', fg=COLORS['gray']).pack(anchor='w', pady=5)
    
    def clear_content(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()
    
    def create_exam(self):
        self.clear_content()
        
        form_frame = tk.Frame(self.content_frame, bg='white')
        form_frame.pack(padx=40, pady=30, fill='both', expand=True)
        
        header_frame = tk.Frame(form_frame, bg='white')
        header_frame.pack(fill='x', pady=(0, 20))
        
        tk.Label(header_frame, text="📝 Create New Exam", font=('Segoe UI', 24, 'bold'), 
                bg='white', fg=COLORS['primary']).pack()
        tk.Label(header_frame, text="Fill in the details to create a new examination", 
                font=('Segoe UI', 10), bg='white', fg=COLORS['gray']).pack()
        
        main_form = tk.Frame(form_frame, bg='white')
        main_form.pack(fill='both', expand=True)
        
        left_column = tk.Frame(main_form, bg='white')
        left_column.pack(side='left', fill='both', expand=True, padx=(0, 20))
        
        details_card = tk.Frame(left_column, bg='#f8f9fa', relief=tk.RAISED, bd=1)
        details_card.pack(fill='x', pady=10)
        
        tk.Label(details_card, text="Exam Information", font=('Segoe UI', 14, 'bold'),
                bg='#f8f9fa', fg=COLORS['dark']).pack(anchor='w', padx=20, pady=(20, 10))
        
        fields = [
            ('Exam Name:', 'exam_name'),
            ('Subject:', 'subject'),
            ('Duration (minutes):', 'duration'),
            ('Total Marks:', 'total_marks'),
            ('Exam Date (YYYY-MM-DD HH:MM):', 'exam_date')
        ]
        
        entries = {}
        for i, (label, key) in enumerate(fields):
            field_frame = tk.Frame(details_card, bg='#f8f9fa')
            field_frame.pack(fill='x', padx=20, pady=10)
            
            tk.Label(field_frame, text=label, font=('Segoe UI', 11),
                    bg='#f8f9fa', fg=COLORS['dark']).pack(anchor='w')
            entry = tk.Entry(field_frame, font=('Segoe UI', 11),
                           bg='white', fg=COLORS['dark'],
                           relief=tk.FLAT, bd=1, highlightthickness=1,
                           highlightcolor=COLORS['primary'])
            entry.pack(fill='x', pady=(5, 0), ipady=6)
            entries[key] = entry
        
        right_column = tk.Frame(main_form, bg='white')
        right_column.pack(side='right', fill='both', expand=True)
        
        questions_card = tk.Frame(right_column, bg='#f8f9fa', relief=tk.RAISED, bd=1)
        questions_card.pack(fill='both', expand=True, pady=10)
        
        tk.Label(questions_card, text="Questions", font=('Segoe UI', 14, 'bold'),
                bg='#f8f9fa', fg=COLORS['dark']).pack(anchor='w', padx=20, pady=(20, 10))
        
        questions_canvas = tk.Canvas(questions_card, bg='#f8f9fa', highlightthickness=0)
        scrollbar = tk.Scrollbar(questions_card, orient='vertical', command=questions_canvas.yview)
        self.questions_frame = tk.Frame(questions_canvas, bg='#f8f9fa')
        
        questions_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        questions_canvas.pack(side='left', fill='both', expand=True, padx=20, pady=10)
        
        canvas_window = questions_canvas.create_window((0, 0), window=self.questions_frame, anchor='nw')
        
        def configure_scroll_region(e):
            questions_canvas.configure(scrollregion=questions_canvas.bbox('all'))
        
        self.questions_frame.bind('<Configure>', configure_scroll_region)
        
        self.questions = []
        
        def add_question():
            question_frame = tk.Frame(self.questions_frame, bg='white', relief=tk.RAISED, bd=1)
            question_frame.pack(fill='x', pady=5, padx=5)
            
            q_num = len(self.questions) + 1
            tk.Label(question_frame, text=f"Question {q_num}", font=('Segoe UI', 11, 'bold'),
                    bg='white', fg=COLORS['primary']).pack(anchor='w', padx=10, pady=(10, 5))
            
            # Question text
            q_entry = tk.Text(question_frame, height=3, width=60, font=('Segoe UI', 10),
                            bg='#f8f9fa', relief=tk.FLAT, bd=1)
            q_entry.pack(padx=10, pady=5, fill='x')
            
            options = []
            options_frame = tk.Frame(question_frame, bg='white')
            options_frame.pack(padx=10, pady=5, fill='x')
            
            for i in range(4):
                opt_frame = tk.Frame(options_frame, bg='white')
                opt_frame.pack(fill='x', pady=2)
                tk.Label(opt_frame, text=f"Option {chr(65+i)}:", font=('Segoe UI', 10),
                        bg='white', width=8, anchor='w').pack(side='left')
                opt_entry = tk.Entry(opt_frame, font=('Segoe UI', 10), bg='#f8f9fa')
                opt_entry.pack(side='left', fill='x', expand=True)
                options.append(opt_entry)
            
            bottom_frame = tk.Frame(question_frame, bg='white')
            bottom_frame.pack(padx=10, pady=5, fill='x')
            
            tk.Label(bottom_frame, text="Correct Answer:", font=('Segoe UI', 10),
                    bg='white').pack(side='left')
            correct_var = tk.StringVar()
            correct_combo = ttk.Combobox(bottom_frame, textvariable=correct_var, 
                                        values=['A', 'B', 'C', 'D'], width=5)
            correct_combo.pack(side='left', padx=(5, 20))
            
            tk.Label(bottom_frame, text="Marks:", font=('Segoe UI', 10),
                    bg='white').pack(side='left')
            marks_entry = tk.Entry(bottom_frame, width=10, font=('Segoe UI', 10))
            marks_entry.pack(side='left', padx=5)
            marks_entry.insert(0, "1")
            
            def remove_question():
                question_frame.destroy()
                self.questions.remove((q_entry, options, correct_var, marks_entry))
            
            remove_btn = tk.Button(question_frame, text="Remove Question", command=remove_question,
                                  bg=COLORS['danger'], fg='white', font=('Segoe UI', 9),
                                  relief=tk.FLAT, cursor='hand2')
            remove_btn.pack(pady=(5, 10))
            
            self.questions.append((q_entry, options, correct_var, marks_entry))
            
            # Update scroll region
            self.questions_frame.update_idletasks()
            questions_canvas.configure(scrollregion=questions_canvas.bbox('all'))
        
        add_btn = tk.Button(questions_card, text="+ Add Question", command=add_question,
                           bg=COLORS['primary'], fg='white', font=('Segoe UI', 10, 'bold'),
                           relief=tk.FLAT, cursor='hand2')
        add_btn.pack(pady=(0, 20))
        
        # Save button
        save_btn = tk.Button(form_frame, text="Save Exam", command=lambda: self.save_exam(entries),
                            bg=COLORS['success'], fg='white', font=('Segoe UI', 12, 'bold'),
                            relief=tk.FLAT, cursor='hand2', width=20, height=1)
        save_btn.pack(pady=20)
    
    def save_exam(self, entries):
        exam_data = {}
        for key, entry in entries.items():
            val = entry.get().strip()
            if not val:
                messagebox.showerror("Error", f"Please fill in: {key.replace('_', ' ').title()}")
                return
            exam_data[key] = val

        # Validate numeric fields
        try:
            duration = int(exam_data['duration'])
            if not (1 <= duration <= 600):
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Duration must be a whole number between 1 and 600 minutes.")
            return

        try:
            total_marks = int(exam_data['total_marks'])
            if not (1 <= total_marks <= 10000):
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Total marks must be a whole number between 1 and 10000.")
            return

        # Validate exam name length
        if len(exam_data['exam_name']) > 200:
            messagebox.showerror("Error", "Exam name is too long (max 200 characters).")
            return

        if not self.questions:
            messagebox.showerror("Error", "Please add at least one question")
            return

        # Prepare questions data
        questions_list = []
        for q_entry, options, correct_var, marks_entry in self.questions:
            question_text = q_entry.get("1.0", tk.END).strip()
            if not question_text:
                messagebox.showerror("Error", "Please enter question text for all questions.")
                return

            option_texts = []
            for opt in options:
                opt_val = opt.get().strip()
                if not opt_val:
                    messagebox.showerror("Error", "Please fill in all answer options.")
                    return
                option_texts.append(opt_val)

            if not correct_var.get():
                messagebox.showerror("Error", "Please select the correct answer for each question.")
                return

            try:
                q_marks = int(marks_entry.get())
                if q_marks < 1:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Error", "Each question must have a positive integer mark value.")
                return

            question = {
                'text': question_text,
                'options': option_texts,
                'correct': correct_var.get(),
                'marks': q_marks
            }
            questions_list.append(question)

        # Save to database
        try:
            conn = DatabaseManager.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO exams (teacher_id, exam_name, subject, duration_minutes,
                                   total_marks, exam_date, questions)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (self.user[0], exam_data['exam_name'], exam_data['subject'],
                  duration, total_marks,
                  exam_data['exam_date'], json.dumps(questions_list)))
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Could not save exam: {e}")
            return

        messagebox.showinfo("Success", "Exam created successfully!")
        self.view_exams()
    
    def view_exams(self):
        self.clear_content()
        
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id, exam_name, subject, duration_minutes, total_marks, exam_date, status FROM exams WHERE teacher_id=?', 
                      (self.user[0],))
        exams = cursor.fetchall()
        conn.close()
        
        if not exams:
            self.show_empty_state("No exams created yet.", "Click 'Create New Exam' to get started")
            return
        
        header_frame = tk.Frame(self.content_frame, bg='white')
        header_frame.pack(fill='x', padx=20, pady=20)
        
        tk.Label(header_frame, text="📋 My Exams", font=('Segoe UI', 20, 'bold'),
                bg='white', fg=COLORS['dark']).pack(anchor='w')
        tk.Label(header_frame, text=f"You have {len(exams)} exam(s) created", 
                font=('Segoe UI', 10), bg='white', fg=COLORS['gray']).pack(anchor='w')
        
        # Treeview with modern styling
        tree_frame = tk.Frame(self.content_frame, bg='white')
        tree_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        # Style for treeview
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Treeview", 
                       background="white",
                       foreground=COLORS['dark'],
                       rowheight=35,
                       fieldbackground="white",
                       font=('Segoe UI', 10))
        style.configure("Treeview.Heading",
                       font=('Segoe UI', 11, 'bold'),
                       foreground=COLORS['dark'],
                       background='#f8f9fa')
        style.map('Treeview', background=[('selected', COLORS['primary'])])
        
        columns = ('ID', 'Exam Name', 'Subject', 'Duration', 'Total Marks', 'Date', 'Status')
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=15)
        
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=150, anchor='center')
        
        for exam in exams:
            tree.insert('', 'end', values=exam)
        
        tree.pack(side='left', fill='both', expand=True)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient='vertical', command=tree.yview)
        scrollbar.pack(side='right', fill='y')
        tree.configure(yscrollcommand=scrollbar.set)
    
    def view_results(self):
        self.clear_content()
        
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT e.exam_name, u.full_name, er.score, er.total_marks, er.submitted_at
            FROM exam_results er
            JOIN exams e ON er.exam_id = e.id
            JOIN users u ON er.student_id = u.id
            WHERE e.teacher_id = ?
            ORDER BY er.submitted_at DESC
        ''', (self.user[0],))
        results = cursor.fetchall()
        conn.close()
        
        if not results:
            self.show_empty_state("No results available.", "Students haven't taken any exams yet")
            return
        
        # Header
        header_frame = tk.Frame(self.content_frame, bg='white')
        header_frame.pack(fill='x', padx=20, pady=20)
        
        tk.Label(header_frame, text="📊 Student Results", font=('Segoe UI', 20, 'bold'),
                bg='white', fg=COLORS['dark']).pack(anchor='w')
        tk.Label(header_frame, text=f"Total submissions: {len(results)}", 
                font=('Segoe UI', 10), bg='white', fg=COLORS['gray']).pack(anchor='w')
        
        # Treeview for results
        tree_frame = tk.Frame(self.content_frame, bg='white')
        tree_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        style = ttk.Style()
        style.configure("Treeview", 
                       background="white",
                       foreground=COLORS['dark'],
                       rowheight=35,
                       fieldbackground="white",
                       font=('Segoe UI', 10))
        style.configure("Treeview.Heading",
                       font=('Segoe UI', 11, 'bold'),
                       foreground=COLORS['dark'],
                       background='#f8f9fa')
        
        columns = ('Exam', 'Student', 'Score', 'Total Marks', 'Percentage', 'Grade', 'Submitted At')
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=15)

        col_widths = [200, 150, 80, 90, 90, 60, 160]
        for col, w in zip(columns, col_widths):
            tree.heading(col, text=col)
            tree.column(col, width=w, anchor='center')

        for result in results:
            # result: (exam_name, full_name, score, total_marks, submitted_at)
            percentage = (result[2] / result[3]) * 100 if result[3] > 0 else 0
            grade = ('A' if percentage >= 90 else 'B' if percentage >= 80 else
                     'C' if percentage >= 70 else 'D' if percentage >= 60 else 'F')
            tree.insert('', 'end', values=(
                result[0], result[1],
                result[2], result[3],
                f"{percentage:.1f}%", grade,
                result[4]
            ))
        
        tree.pack(side='left', fill='both', expand=True)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient='vertical', command=tree.yview)
        scrollbar.pack(side='right', fill='y')
        tree.configure(yscrollcommand=scrollbar.set)
    
    def view_logs(self):
        self.clear_content()
        
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT a.violation_type, u.full_name, e.exam_name, a.violation_details, a.timestamp
            FROM anti_cheat_logs a
            JOIN users u ON a.student_id = u.id
            JOIN exams e ON a.exam_id = e.id
            WHERE e.teacher_id = ?
            ORDER BY a.timestamp DESC
        ''', (self.user[0],))
        logs = cursor.fetchall()
        conn.close()
        
        if not logs:
            self.show_empty_state("No anti-cheat logs available.", "No violations detected yet")
            return
        
        # Header
        header_frame = tk.Frame(self.content_frame, bg='white')
        header_frame.pack(fill='x', padx=20, pady=20)
        
        tk.Label(header_frame, text="🔒 Anti-Cheat Violation Logs", font=('Segoe UI', 20, 'bold'),
                bg='white', fg=COLORS['danger']).pack(anchor='w')
        tk.Label(header_frame, text=f"Total violations: {len(logs)}", 
                font=('Segoe UI', 10), bg='white', fg=COLORS['gray']).pack(anchor='w')
        
        # Treeview for logs
        tree_frame = tk.Frame(self.content_frame, bg='white')
        tree_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        style = ttk.Style()
        style.configure("Treeview", 
                       background="white",
                       foreground=COLORS['dark'],
                       rowheight=35,
                       fieldbackground="white",
                       font=('Segoe UI', 10))
        style.configure("Treeview.Heading",
                       font=('Segoe UI', 11, 'bold'),
                       foreground=COLORS['dark'],
                       background='#f8f9fa')
        
        columns = ('Violation Type', 'Student', 'Exam', 'Details', 'Timestamp')
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=15)
        
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=180, anchor='center')
        
        for log in logs:
            tree.insert('', 'end', values=log)
        
        tree.pack(side='left', fill='both', expand=True)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient='vertical', command=tree.yview)
        scrollbar.pack(side='right', fill='y')
        tree.configure(yscrollcommand=scrollbar.set)
    
    def show_empty_state(self, title, message):
        empty_frame = tk.Frame(self.content_frame, bg='white')
        empty_frame.pack(expand=True, fill='both')
        
        tk.Label(empty_frame, text="📭", font=('Segoe UI', 64),
                bg='white', fg=COLORS['gray']).pack(pady=(50, 20))
        tk.Label(empty_frame, text=title, font=('Segoe UI', 18, 'bold'),
                bg='white', fg=COLORS['dark']).pack()
        tk.Label(empty_frame, text=message, font=('Segoe UI', 11),
                bg='white', fg=COLORS['gray']).pack(pady=10)
    
    def logout(self):
        if not messagebox.askyesno("Logout", "Are you sure you want to log out?"):
            return
        self.root.destroy()
        root = tk.Tk()
        RoleSelectionWindow(root)
        root.mainloop()

class StudentDashboard:
    def __init__(self, user):
        self.user = user
        self.root = tk.Tk()
        self.root.title(f"Student Dashboard - {user[3]}")
        self.root.geometry("1200x700")
        self.root.configure(bg=COLORS['light'])
        
        # Create menu bar
        menubar = tk.Menu(self.root, bg=COLORS['white'], fg=COLORS['dark'])
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0, bg=COLORS['white'], fg=COLORS['dark'])
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Logout", command=self.logout)
        file_menu.add_command(label="Exit", command=self.root.quit)
        
        # Header
        header_frame = tk.Frame(self.root, bg=COLORS['primary'], height=80)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)

        # RIGHT: Logout button (packed first so title centering works correctly)
        logout_btn = tk.Button(header_frame, text="Logout",
                               font=('Segoe UI', 11, 'bold'),
                               bg=COLORS['danger'], fg='white',
                               relief=tk.FLAT, cursor='hand2',
                               padx=14, pady=6, command=self.logout)
        logout_btn.pack(side='right', padx=20, pady=20)
        logout_btn.bind('<Enter>', lambda e: logout_btn.configure(bg='#b01050'))
        logout_btn.bind('<Leave>', lambda e: logout_btn.configure(bg=COLORS['danger']))

        # LEFT: Welcome + name
        welcome_frame = tk.Frame(header_frame, bg=COLORS['primary'])
        welcome_frame.pack(side='left', padx=24, pady=14)
        tk.Label(welcome_frame, text="Welcome back,",
                 font=('Segoe UI', 11), bg=COLORS['primary'],
                 fg='#d0e8ff', anchor='w').pack(anchor='w')
        tk.Label(welcome_frame, text=str(user[3]),
                 font=('Segoe UI', 17, 'bold'), bg=COLORS['primary'],
                 fg='white', anchor='w').pack(anchor='w')

        # CENTER: Dashboard title (placed so it is always centered over the full header width)
        tk.Label(header_frame, text="Student Dashboard",
                 font=('Segoe UI', 18, 'bold'),
                 bg=COLORS['primary'], fg='white').place(relx=0.5, rely=0.5, anchor='center')

        # Stats cards (clickable)
        stats_frame = tk.Frame(self.root, bg=COLORS['light'], height=120)
        stats_frame.pack(fill='x', padx=20, pady=20)
        stats_frame.pack_propagate(False)

        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM exam_results WHERE student_id=?', (self.user[0],))
        exams_taken = cursor.fetchone()[0]
        cursor.execute('SELECT AVG((score * 100.0) / total_marks) FROM exam_results WHERE student_id=? AND total_marks>0', (self.user[0],))
        avg_score = cursor.fetchone()[0]
        avg_score = int(avg_score) if avg_score else 0
        cursor.execute('SELECT COUNT(*) FROM exams WHERE id NOT IN (SELECT exam_id FROM exam_results WHERE student_id=?) AND status="pending"', (self.user[0],))
        available_exams = cursor.fetchone()[0]
        conn.close()

        stats = [
            ('📚 Exams Taken',    exams_taken,          COLORS['primary'], self.show_results),
            ('📊 Average Score',  f"{avg_score}%",       COLORS['success'], self.show_results),
            ('🎯 Available Exams', available_exams,      COLORS['warning'], self.show_available_exams),
        ]

        for i, (title, value, color, action) in enumerate(stats):
            card = tk.Frame(stats_frame, bg='white', relief=tk.FLAT, bd=0,
                            cursor='hand2',
                            highlightbackground='#e0e0e0', highlightthickness=1)
            card.place(x=i * 260 + 20, y=10, width=235, height=90)

            title_lbl = tk.Label(card, text=title, font=('Segoe UI', 10),
                                 bg='white', fg=COLORS['gray'], cursor='hand2')
            title_lbl.place(x=15, y=10)

            val_lbl = tk.Label(card, text=str(value), font=('Segoe UI', 26, 'bold'),
                               bg='white', fg=color, cursor='hand2')
            val_lbl.place(x=15, y=35)

            hint_lbl = tk.Label(card, text="", font=('Segoe UI', 8, 'italic'),
                                bg='white', fg='#aaaaaa', cursor='hand2')
            hint_lbl.place(x=15, y=68)

            def _on_enter(e, c=card, clr=color):
                c.configure(highlightbackground=clr, highlightthickness=2)
            def _on_leave(e, c=card):
                c.configure(highlightbackground='#e0e0e0', highlightthickness=1)

            for widget in (card, title_lbl, val_lbl, hint_lbl):
                widget.bind('<Button-1>', lambda e, fn=action: fn())
                widget.bind('<Enter>', _on_enter)
                widget.bind('<Leave>', _on_leave)
        
        # Main content frame
        self.main_frame = tk.Frame(self.root, bg=COLORS['light'])
        self.main_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        # Navigation buttons
        nav_frame = tk.Frame(self.main_frame, bg=COLORS['light'])
        nav_frame.pack(fill='x', pady=(0, 20))
        
        buttons = [
            ('📝 Available Exams', self.show_available_exams, COLORS['primary']),
            ('📊 My Results', self.show_results, COLORS['success']),
            ('🗑️ Clear Logs', self.clear_logs, COLORS['danger'])
        ]
        
        for text, command, color in buttons:
            btn = tk.Button(nav_frame, text=text, font=('Segoe UI', 11, 'bold'),
                           bg=color, fg='white', relief=tk.FLAT, cursor='hand2',
                           padx=20, pady=10, command=command)
            btn.pack(side='left', padx=5)
            btn.bind('<Enter>', lambda e, c=color: e.widget.configure(bg=self.darken_color(c)))
            btn.bind('<Leave>', lambda e, c=color: e.widget.configure(bg=c))
        
        # Content area
        self.content_frame = tk.Frame(self.main_frame, bg='white', relief=tk.FLAT, bd=0)
        self.content_frame.pack(fill='both', expand=True)
        self.content_frame.configure(highlightbackground=COLORS['gray'], highlightthickness=1)
        
        self.show_available_exams()
        
        self.root.mainloop()
    
    def darken_color(self, color):
        return COLORS['secondary'] if color == COLORS['primary'] else \
               '#3aa8c5' if color == COLORS['success'] else \
               '#e07a1a'
    
    def clear_content(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()
    
    def show_available_exams(self):
        self.clear_content()
        
        # Get exams that student hasn't taken yet
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, exam_name, subject, duration_minutes, total_marks, exam_date 
            FROM exams 
            WHERE id NOT IN (
                SELECT exam_id FROM exam_results WHERE student_id = ?
            )
            AND status = 'pending'
        ''', (self.user[0],))
        
        exams = cursor.fetchall()
        conn.close()
        
        if not exams:
            self.show_empty_state("No available exams", "Check back later for new exams")
            return
        
        # Header
        header_frame = tk.Frame(self.content_frame, bg='white')
        header_frame.pack(fill='x', padx=20, pady=20)
        
        tk.Label(header_frame, text="📝 Available Exams", font=('Segoe UI', 20, 'bold'),
                bg='white', fg=COLORS['dark']).pack(anchor='w')
        tk.Label(header_frame, text=f"You have {len(exams)} exam(s) available to take", 
                font=('Segoe UI', 10), bg='white', fg=COLORS['gray']).pack(anchor='w')
        
        # Display exams in cards
        for exam in exams:
            exam_card = tk.Frame(self.content_frame, bg='white', relief=tk.RAISED, bd=1)
            exam_card.pack(fill='x', padx=20, pady=10)
            
            # Left side - exam info
            info_frame = tk.Frame(exam_card, bg='white')
            info_frame.pack(side='left', fill='both', expand=True, padx=20, pady=15)
            
            tk.Label(info_frame, text=exam[1], font=('Segoe UI', 16, 'bold'), 
                    bg='white', fg=COLORS['primary']).pack(anchor='w')
            
            details = f"📖 Subject: {exam[2]}  |  ⏱️ Duration: {exam[3]} mins  |  📊 Total Marks: {exam[4]}  |  📅 Date: {exam[5]}"
            tk.Label(info_frame, text=details, font=('Segoe UI', 10), 
                    bg='white', fg=COLORS['gray']).pack(anchor='w', pady=(5, 0))
            
            # Right side - start button
            start_btn = tk.Button(exam_card, text="Start Exam →",
                                 command=lambda e=exam: self.start_exam(e),
                                 bg=COLORS['success'], fg='white',
                                 font=('Segoe UI', 11, 'bold'),
                                 relief=tk.FLAT, cursor='hand2',
                                 padx=20, pady=8)
            start_btn.pack(side='right', padx=20)
            start_btn.bind('<Enter>', lambda e, b=start_btn: b.configure(bg='#3aa8c5'))
            start_btn.bind('<Leave>', lambda e, b=start_btn: b.configure(bg=COLORS['success']))
    
    def show_results(self):
        self.clear_content()
        
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT e.exam_name, er.score, er.total_marks, er.submitted_at
            FROM exam_results er
            JOIN exams e ON er.exam_id = e.id
            WHERE er.student_id = ?
            ORDER BY er.submitted_at DESC
        ''', (self.user[0],))
        
        results = cursor.fetchall()
        conn.close()
        
        if not results:
            self.show_empty_state("No results available", "Take an exam to see your results here")
            return
        
        # Header
        header_frame = tk.Frame(self.content_frame, bg='white')
        header_frame.pack(fill='x', padx=20, pady=20)
        
        tk.Label(header_frame, text="📊 My Results", font=('Segoe UI', 20, 'bold'),
                bg='white', fg=COLORS['dark']).pack(anchor='w')
        tk.Label(header_frame, text=f"You have taken {len(results)} exam(s)", 
                font=('Segoe UI', 10), bg='white', fg=COLORS['gray']).pack(anchor='w')
        
        # Treeview for results
        tree_frame = tk.Frame(self.content_frame, bg='white')
        tree_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        style = ttk.Style()
        style.configure("Treeview", 
                       background="white",
                       foreground=COLORS['dark'],
                       rowheight=35,
                       fieldbackground="white",
                       font=('Segoe UI', 10))
        style.configure("Treeview.Heading",
                       font=('Segoe UI', 11, 'bold'),
                       foreground=COLORS['dark'],
                       background='#f8f9fa')
        
        columns = ('Exam Name', 'Score', 'Total Marks', 'Percentage', 'Submitted At')
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=15)
        
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=180, anchor='center')
        
        for result in results:
            percentage = (result[1] / result[2]) * 100 if result[2] > 0 else 0
            # Add color coding for percentage
            tree.insert('', 'end', values=(result[0], result[1], result[2], 
                                          f"{percentage:.1f}%", result[3]))
        
        tree.pack(side='left', fill='both', expand=True)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient='vertical', command=tree.yview)
        scrollbar.pack(side='right', fill='y')
        tree.configure(yscrollcommand=scrollbar.set)
    
    def show_empty_state(self, title, message):
        empty_frame = tk.Frame(self.content_frame, bg='white')
        empty_frame.pack(expand=True, fill='both')
        
        tk.Label(empty_frame, text="📭", font=('Segoe UI', 64),
                bg='white', fg=COLORS['gray']).pack(pady=(50, 20))
        tk.Label(empty_frame, text=title, font=('Segoe UI', 18, 'bold'),
                bg='white', fg=COLORS['dark']).pack()
        tk.Label(empty_frame, text=message, font=('Segoe UI', 11),
                bg='white', fg=COLORS['gray']).pack(pady=10)
    
    def start_exam(self, exam):
        # Check if exam date has passed
        try:
            exam_datetime = datetime.datetime.strptime(exam[5], "%Y-%m-%d %H:%M")
            if exam_datetime < datetime.datetime.now():
                messagebox.showerror("Exam Unavailable",
                                     "This exam has already passed its scheduled time.")
                return
        except ValueError:
            pass  # Date format may vary; allow exam to proceed

        # Confirm before starting (anti-cheat will lock the window)
        if not messagebox.askyesno("Start Exam",
                                   f"You are about to start:\n\n  {exam[1]}\n\n"
                                   f"Duration: {exam[3]} minutes\n"
                                   "The window will enter full-screen mode.\n\n"
                                   "Are you ready?"):
            return

        exam_window = tk.Toplevel(self.root)
        ExamWindow(exam_window, self.user, exam, parent_dashboard=self.root)
    
    def clear_logs(self):
        """Clear all stored anti-cheat logs for this student"""
        result = messagebox.askyesno("Clear Logs",
                                     "Are you sure you want to clear all your stored anti-cheat logs?\n\n"
                                     "This action cannot be undone.")
        if not result:
            return
        
        try:
            conn = DatabaseManager.get_connection()
            cursor = conn.cursor()
            # Delete all anti-cheat logs for this student
            cursor.execute('DELETE FROM anti_cheat_logs WHERE student_id=?', (self.user[0],))
            conn.commit()
            conn.close()
            messagebox.showinfo("Success", "All your stored logs have been cleared successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to clear logs: {e}")
    
    def logout(self):
        if not messagebox.askyesno("Logout", "Are you sure you want to log out?"):
            return
        self.root.destroy()
        root = tk.Tk()
        RoleSelectionWindow(root)
        root.mainloop()

class ExamWindow:
    def __init__(self, parent, user, exam, parent_dashboard=None):
        self.parent = parent
        self.user = user
        self.exam = exam
        self.parent_dashboard = parent_dashboard
        self.current_question = 0
        self.answers = {}
        self.anti_cheat = None

        # Setup exam window
        self.window = tk.Toplevel(parent)
        self.window.title(f"Exam: {exam[1]}")
        self.window.geometry("1000x700")
        self.window.configure(bg=COLORS['light'])

        # Fullscreen — fail gracefully on platforms that don't support it
        try:
            self.window.attributes('-fullscreen', True)
        except tk.TclError:
            self.window.state('zoomed')

        self.window.protocol("WM_DELETE_WINDOW", self.prevent_close)
        
        # Load exam questions
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT questions FROM exams WHERE id=?', (exam[0],))
        result = cursor.fetchone()
        conn.close()
        
        self.questions = json.loads(result[0])
        self.total_questions = len(self.questions)
        
        # Start timer
        self.time_left = int(exam[3]) * 60  # Convert to seconds
        
        # Initialize anti-cheat
        self.init_anti_cheat()
        
        # Create UI
        self.create_exam_ui()
        
        # Start timer
        self.update_timer()
    
    def init_anti_cheat(self):
        """Initialize anti-cheat system"""
        try:
            if ANTI_CHEAT_AVAILABLE:
                self.anti_cheat = AntiCheatSystem(self.window, self.user[0], self.exam[0])
                self.anti_cheat.start_monitoring()
        except Exception as e:
            print(f"Anti-cheat initialization warning: {e}")
    
    def prevent_close(self):
        """Prevent closing the exam window"""
        messagebox.showwarning("Warning", "You cannot close the exam window during the exam!")
    
    def create_exam_ui(self):
        # Header frame
        header_frame = tk.Frame(self.window, bg=COLORS['primary'], height=70)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)
        
        tk.Label(header_frame, text=f"📝 {self.exam[1]}", 
                font=('Segoe UI', 16, 'bold'), bg=COLORS['primary'], fg='white').pack(side='left', padx=30, pady=15)
        
        self.timer_label = tk.Label(header_frame, text="Time Left: ", 
                                   font=('Segoe UI', 16, 'bold'), bg=COLORS['primary'], fg='white')
        self.timer_label.pack(side='right', padx=30, pady=15)
        
        # Progress bar
        progress_frame = tk.Frame(self.window, bg=COLORS['light'], height=40)
        progress_frame.pack(fill='x', padx=30, pady=10)
        
        self.progress_label = tk.Label(progress_frame, text=f"Question 1 of {self.total_questions}",
                                      font=('Segoe UI', 10), bg=COLORS['light'], fg=COLORS['gray'])
        self.progress_label.pack()
        
        self.progress_bar = ttk.Progressbar(progress_frame, length=800, mode='determinate')
        self.progress_bar.pack(pady=5)
        self.progress_bar['maximum'] = self.total_questions
        self.progress_bar['value'] = 1
        
        # Question frame
        self.question_frame = tk.Frame(self.window, bg='white', relief=tk.RAISED, bd=1)
        self.question_frame.pack(fill='both', expand=True, padx=30, pady=20)
        
        self.display_question()
        
        # Navigation frame
        nav_frame = tk.Frame(self.window, bg=COLORS['light'], height=80)
        nav_frame.pack(fill='x')
        nav_frame.pack_propagate(False)
        
        prev_btn = tk.Button(nav_frame, text="← Previous", command=self.prev_question,
                            font=('Segoe UI', 11), bg=COLORS['gray'], fg='white',
                            relief=tk.FLAT, cursor='hand2', padx=20, pady=8)
        prev_btn.pack(side='left', padx=30, pady=10)
        prev_btn.bind('<Enter>', lambda e: prev_btn.configure(bg='#5a6268'))
        prev_btn.bind('<Leave>', lambda e: prev_btn.configure(bg=COLORS['gray']))
        
        next_btn = tk.Button(nav_frame, text="Next →", command=self.next_question,
                            font=('Segoe UI', 11), bg=COLORS['primary'], fg='white',
                            relief=tk.FLAT, cursor='hand2', padx=20, pady=8)
        next_btn.pack(side='right', padx=30, pady=10)
        next_btn.bind('<Enter>', lambda e: next_btn.configure(bg=COLORS['secondary']))
        next_btn.bind('<Leave>', lambda e: next_btn.configure(bg=COLORS['primary']))
        
        submit_btn = tk.Button(nav_frame, text="Submit Exam ✓", command=self.submit_exam,
                              font=('Segoe UI', 11, 'bold'), bg=COLORS['success'], fg='white',
                              relief=tk.FLAT, cursor='hand2', padx=30, pady=8)
        submit_btn.pack(pady=10)
        submit_btn.bind('<Enter>', lambda e: submit_btn.configure(bg='#3aa8c5'))
        submit_btn.bind('<Leave>', lambda e: submit_btn.configure(bg=COLORS['success']))
    
    def display_question(self):
        # Clear frame
        for widget in self.question_frame.winfo_children():
            widget.destroy()
        
        question_data = self.questions[self.current_question]
        
        # Update progress
        self.progress_label.config(text=f"Question {self.current_question + 1} of {self.total_questions}")
        self.progress_bar['value'] = self.current_question + 1
        
        # Question card
        card_frame = tk.Frame(self.question_frame, bg='white')
        card_frame.pack(fill='both', expand=True, padx=30, pady=30)
        
        # Question number badge
        badge = tk.Label(card_frame, text=f"Question {self.current_question + 1}",
                        font=('Segoe UI', 11, 'bold'), bg=COLORS['primary'], fg='white',
                        padx=15, pady=5)
        badge.pack(anchor='w')
        
        # Marks
        tk.Label(card_frame, text=f"Marks: {question_data['marks']}", 
                font=('Segoe UI', 10), bg='white', fg=COLORS['gray']).pack(anchor='w', pady=(5, 15))
        
        # Question text
        q_frame = tk.Frame(card_frame, bg='#f8f9fa', relief=tk.RAISED, bd=1)
        q_frame.pack(fill='x', pady=10)
        
        q_text = tk.Label(q_frame, text=question_data['text'],
                         font=('Segoe UI', 12), bg='#f8f9fa', fg=COLORS['dark'],
                         wraplength=800, justify='left', padx=20, pady=20)
        q_text.pack()
        
        # Options
        options_frame = tk.Frame(card_frame, bg='white')
        options_frame.pack(fill='x', pady=20)
        
        self.selected_option = tk.StringVar()
        
        # Load saved answer if exists
        if self.current_question in self.answers:
            self.selected_option.set(self.answers[self.current_question])
        
        for i, option in enumerate(question_data['options']):
            option_text = f"{chr(65+i)}. {option}"
            rb = tk.Radiobutton(options_frame, text=option_text, 
                               variable=self.selected_option, value=chr(65+i),
                               font=('Segoe UI', 11), bg='white', fg=COLORS['dark'],
                               anchor='w', selectcolor='white',
                               command=self.save_answer)
            rb.pack(anchor='w', pady=8)
    
    def save_answer(self):
        self.answers[self.current_question] = self.selected_option.get()
    
    def next_question(self):
        if self.current_question < self.total_questions - 1:
            self.current_question += 1
            self.display_question()
    
    def prev_question(self):
        if self.current_question > 0:
            self.current_question -= 1
            self.display_question()
    
    def update_timer(self):
        if self.time_left <= 0:
            self._force_submit()
            return

        minutes = self.time_left // 60
        seconds = self.time_left % 60
        self.timer_label.config(text=f"⏱️ Time Left: {minutes:02d}:{seconds:02d}")

        if self.time_left < 300:  # 5 minutes
            self.timer_label.config(fg=COLORS['danger'])

        self.time_left -= 1
        self.window.after(1000, self.update_timer)

    def _force_submit(self):
        """Called when timer runs out — no confirmation prompt."""
        messagebox.showwarning("Time Up", "⏰ Time is up! Your exam is being submitted automatically.")
        self._do_submit()

    def submit_exam(self):
        """Called by the Submit button — asks for confirmation first."""
        result = messagebox.askyesno("Confirm Submission",
                                     "Are you sure you want to submit the exam?\n\n"
                                     "You will not be able to change your answers after submitting.")
        if not result:
            return
        self._do_submit()

    def _do_submit(self):
        """Core submission logic shared by manual submit and auto-submit."""
        # Stop timer callbacks firing again
        self.time_left = 0

        # Calculate score
        total_score = 0
        for i, q in enumerate(self.questions):
            if i in self.answers and self.answers[i] == q['correct']:
                total_score += q['marks']

        # Persist result
        try:
            conn = DatabaseManager.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO exam_results (student_id, exam_id, score, total_marks, answers)
                VALUES (?, ?, ?, ?, ?)
            ''', (self.user[0], self.exam[0], total_score, self.exam[4],
                  json.dumps(self.answers)))
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            messagebox.showerror("Error", f"Could not save exam results: {e}")
            return

        # Stop anti-cheat monitoring
        if self.anti_cheat:
            self.anti_cheat.stop_monitoring()

        # Show results
        total_marks = self.exam[4]
        percentage = (total_score / total_marks) * 100 if total_marks > 0 else 0
        grade = ('A' if percentage >= 90 else
                 'B' if percentage >= 80 else
                 'C' if percentage >= 70 else
                 'D' if percentage >= 60 else 'F')
        feedback = ('🎉 Excellent work!' if percentage >= 80 else
                    '👍 Good job!' if percentage >= 60 else
                    '📚 Keep practicing!')

        result_message = (
            f"📊 Exam Results\n\n"
            f"Score: {total_score}/{total_marks}\n"
            f"Percentage: {percentage:.1f}%\n"
            f"Grade: {grade}\n\n"
            f"{feedback}"
        )
        messagebox.showinfo("Exam Submitted", result_message)

        self.window.destroy()
        # Refresh parent student dashboard
        try:
            if self.parent_dashboard:
                self.parent_dashboard.destroy()
        except Exception:
            pass
        root = tk.Tk()
        StudentDashboard(self.user)

# Main execution
if __name__ == "__main__":
    # Initialize database
    DatabaseManager.initialize_database()
    
    # Create main window with role selection
    root = tk.Tk()
    role_selection = RoleSelectionWindow(root)
    root.mainloop()
