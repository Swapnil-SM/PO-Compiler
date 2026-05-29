import tkinter as tk
from tkinter import messagebox, filedialog
from datetime import datetime
from tkinter import ttk
import time
import threading
import sys
import os
from log_uploader import upload_logs_to_s3

import requests
from PIL import Image, ImageTk
from io import BytesIO
import subprocess
import logging
import io
from contextlib import redirect_stdout, redirect_stderr

from llm_call import run_llm_po
import gspread
from google.oauth2.service_account import Credentials

from local_db import create_tables, sync_sku_master


# Redirect stdout and stderr to null if running without a console
if sys.executable.endswith("pythonw.exe"):
    sys.stdout = open(os.devnull, "w")
    sys.stderr = open(os.devnull, "w")

sys.path.append("Z:\\airflow\\scripts\\POcompilation\\")
sys.path.append('/opt/airflow/scripts/Pocompilation/')

if getattr(sys, 'frozen', False):
    script_dir = sys._MEIPASS
else:
    script_dir = os.path.dirname(os.path.abspath(__file__))

SERVICE_ACCOUNT_FILE = os.path.join(script_dir, 'starlit-tangent-411613-a5467af2ab19.json')
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key("1IJ2Vlx-tjiARH9ZwzK2807Du-xRQ-nUwH60q_D0Cc8I")
sheet = spreadsheet.worksheet("email_control")
retailer_sheet = spreadsheet.worksheet("retailers")

# ================= DB INITIALIZATION =================
create_tables()
sync_sku_master()

# Load retailer list + mode
retailer_data = retailer_sheet.get_all_records(expected_headers=["retailer_name", "mode"])

retailer_modes = {
    row['retailer_name'].strip().upper(): row['mode'].strip().upper()
    for row in retailer_data
}



function_map = {
    "RELIANCE RETAIL LIMITED": run_llm_po,
    "METRO CASH AND CARRY INDIA LIMITED": run_llm_po,
    "MORE RETAIL PRIVATE LIMITED": run_llm_po
}

class LogCapture:
    """Custom class to capture print statements and logs"""
    def __init__(self):
        self.logs = []
        self.original_stdout = sys.stdout if sys.stdout else None
        self.original_stderr = sys.stderr


    def write(self, text):
        if self.original_stdout:
            try:
                self.original_stdout.write(text)
            except:
                pass

        try:
            self.widget.insert(tk.END, text)
            self.widget.see(tk.END)
        except:
            pass

    def flush(self):
        self.original_stdout.flush()
        
    def get_logs(self):
        return "\n".join(self.logs)
        
    def clear_logs(self):
        self.logs.clear()

class ModernPOCompiler:
    def __init__(self, root):
        self.root = root
        self.logo_image = None
        self.cmd_process = None
        self.logs_visible = False
        self.log_window = None
        self.log_capture = LogCapture()
        
        # Redirect stdout to capture prints
        sys.stdout = self.log_capture
        
        self.setup_logging()
        self.setup_window()
        self.load_logo()
        self.setup_styles()
        self.create_widgets()
        
    def setup_window(self):
        self.root.title("PO Compiler Pro")
        self.root.geometry("800x650")
        self.root.configure(bg="#f8fafc")
        self.root.resizable(False, False)
        
        # Center the window
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
        
    def load_logo(self):
        """Load logo from URL"""
        try:
            logo_url = "https://d3ve5430cjjm40.cloudfront.net/InsytPro_Logo_White.png"
            response = requests.get(logo_url, timeout=10)
            if response.status_code == 200:
                image = Image.open(BytesIO(response.content))
                # Resize logo to fit nicely in header
                image = image.resize((120, 40), Image.Resampling.LANCZOS)
                self.logo_image = ImageTk.PhotoImage(image)
        except Exception as e:
            print(f"Could not load logo: {e}")
            self.logo_image = None
            
        # Load and set window icon
        try:
            icon_url = "https://d3ve5430cjjm40.cloudfront.net/Insyt%20Logo.png"
            icon_response = requests.get(icon_url, timeout=10)
            if icon_response.status_code == 200:
                icon_image = Image.open(BytesIO(icon_response.content))
                # Resize icon for window (typically 32x32 or 16x16)
                icon_image = icon_image.resize((32, 32), Image.Resampling.LANCZOS)
                icon_photo = ImageTk.PhotoImage(icon_image)
                self.root.iconphoto(True, icon_photo)
        except Exception as e:
            print(f"Could not load window icon: {e}")

    def setup_logging(self):
        """Setup logging configuration (safe for EXE)"""

        # Detect base directory (EXE or script)
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        # Logs directory next to EXE
        log_dir = os.path.join(base_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)

        log_filename = os.path.join(
            log_dir,
            f"po_compiler_{datetime.now().strftime('%Y%m%d')}.log"
        )

        # Custom handler for UI log capture
        class LogHandler(logging.Handler):
            def __init__(self, log_capture):
                super().__init__()
                self.log_capture = log_capture

            def emit(self, record):
                log_entry = self.format(record)
                self.log_capture.logs.append(log_entry)

        # Reset logging (important for EXE)
        logging.getLogger().handlers.clear()

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_filename, encoding="utf-8"),
                LogHandler(self.log_capture)
            ]
        )

        self.logger = logging.getLogger("POCompiler")
        self.logger.info("PO Compiler application started")

    def toggle_logs(self):
        """Toggle log window"""
        if not self.logs_visible:
            self.show_logs()
        else:
            self.hide_logs()
            
    def show_logs(self):
        """Show logs in a new window"""
        if self.log_window is None or not self.log_window.winfo_exists():
            self.log_window = tk.Toplevel(self.root)
            self.log_window.title("PO Compiler Logs")
            self.log_window.geometry("800x500")
            self.log_window.configure(bg="#1e293b")
            
            # Create header
            header_frame = tk.Frame(self.log_window, bg="#334155", height=40)
            header_frame.pack(fill=tk.X)
            header_frame.pack_propagate(False)
            
            title_label = tk.Label(header_frame, text="📋 PO Compiler Logs", 
                                 font=("Consolas", 12, "bold"), 
                                 fg="#f1f5f9", bg="#334155")
            title_label.pack(side=tk.LEFT, padx=15, pady=10)
            
            # Clear logs button
            clear_btn = tk.Button(header_frame, text="🗑️ Clear", 
                                command=self.clear_logs,
                                font=("Segoe UI", 9),
                                bg="#ef4444", fg="white",
                                border=0, padx=15, pady=5)
            clear_btn.pack(side=tk.RIGHT, padx=15, pady=8)
            
            # Create text widget with scrollbar
            text_frame = tk.Frame(self.log_window, bg="#1e293b")
            text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # Scrollbar
            scrollbar = tk.Scrollbar(text_frame)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # Text widget
            self.log_text = tk.Text(text_frame, 
                                  bg="#0f172a", 
                                  fg="#e2e8f0",
                                  font=("Consolas", 10),
                                  yscrollcommand=scrollbar.set,
                                  wrap=tk.WORD,
                                  padx=15,
                                  pady=15)
            self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.config(command=self.log_text.yview)
            
            # Handle window close
            self.log_window.protocol("WM_DELETE_WINDOW", self.hide_logs)
            
        # Update logs content
        self.update_log_display()
        
        self.logs_visible = True
        self.logs_btn.config(text="🔍 Hide Logs")
        self.logger.info("Log viewer opened")
        
        # Start auto-refresh
        self.auto_refresh_logs()
        
    def hide_logs(self):
        """Hide the log window"""
        if self.log_window and self.log_window.winfo_exists():
            self.log_window.destroy()
            
        self.logs_visible = False
        self.logs_btn.config(text="📋 Show Logs")
        self.logger.info("Log viewer closed")
        
    def clear_logs(self):
        """Clear all logs"""
        self.log_capture.clear_logs()
        if self.logs_visible and self.log_window and self.log_window.winfo_exists():
            self.log_text.delete(1.0, tk.END)
            self.log_text.insert(tk.END, "Logs cleared.\n")
        self.logger.info("Logs cleared by user")
        
    def update_log_display(self):
        """Update the log display with current logs"""
        if self.logs_visible and self.log_window and self.log_window.winfo_exists():
            current_logs = self.log_capture.get_logs()
            
            # Clear and insert new content
            self.log_text.delete(1.0, tk.END)
            if current_logs:
                self.log_text.insert(tk.END, current_logs)
            else:
                self.log_text.insert(tk.END, "No logs yet. Generate an email to see logs here.")
                
            # Auto-scroll to bottom
            self.log_text.see(tk.END)
            
    def auto_refresh_logs(self):
        """Auto-refresh logs every 1 second when window is visible"""
        if self.logs_visible and self.log_window and self.log_window.winfo_exists():
            self.update_log_display()
            # Schedule next refresh
            self.root.after(1000, self.auto_refresh_logs)
            
    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure modern button style
        style.configure('Modern.TButton',
                       background='#3b82f6',
                       foreground='white',
                       borderwidth=0,
                       focuscolor='none',
                       padding=(20, 12))
        
        style.map('Modern.TButton',
                 background=[('active', '#2563eb'),
                           ('pressed', '#1d4ed8')])
        
        # Configure success button style
        style.configure('Success.TButton',
                       background='#10b981',
                       foreground='white',
                       borderwidth=0,
                       focuscolor='none',
                       padding=(15, 10))
        
        style.map('Success.TButton',
                 background=[('active', '#059669'),
                           ('pressed', '#047857')])
        
        # Configure modern combobox
        style.configure('Modern.TCombobox',
                       fieldbackground='white',
                       background='white',
                       borderwidth=1,
                       relief='solid',
                       padding=8)
        
        # Configure modern entry
        style.configure('Modern.TEntry',
                       fieldbackground='white',
                       borderwidth=1,
                       relief='solid',
                       padding=8)
        
        # Configure logs button style
        style.configure('Logs.TButton',
                       background='#6366f1',
                       foreground='white',
                       borderwidth=0,
                       focuscolor='none',
                       padding=(12, 8))
        
        style.map('Logs.TButton',
                 background=[('active', '#4f46e5'),
                           ('pressed', '#4338ca')])
        
    def create_widgets(self):
        # Main container with less padding
        main_frame = tk.Frame(self.root, bg="#f8fafc")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        
        # Header - more compact
        self.create_header(main_frame)
        
        # Content area with shadow effect
        content_frame = tk.Frame(main_frame, bg="white", relief="flat")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=(10, 0))
        
        # Add shadow effect by creating a slightly larger dark frame behind
        shadow_frame = tk.Frame(main_frame, bg="#d1d5db", height=2)
        shadow_frame.pack(fill=tk.X, pady=(0, 2))
        
        # Create form sections
        self.create_form_sections(content_frame)
        
    def create_header(self, parent):
        header_frame = tk.Frame(parent, bg="#f8fafc")
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Top header with logo, title, and logs button
        top_header = tk.Frame(header_frame, bg="#f8fafc")
        top_header.pack(fill=tk.X, pady=(0, 5))
        
        # Logo on the left
        if self.logo_image:
            logo_label = tk.Label(top_header, image=self.logo_image, bg="#f8fafc")
            logo_label.pack(side=tk.LEFT, padx=(0, 15))
        
        # Logs button on the right
        self.logs_btn = ttk.Button(top_header, text="📋 Show Logs", 
                                  command=self.toggle_logs,
                                  style='Logs.TButton')
        self.logs_btn.pack(side=tk.RIGHT)
        
        # Title and subtitle container (centered)
        title_container = tk.Frame(top_header, bg="#f8fafc")
        title_container.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Title - centered
        title_label = tk.Label(title_container, 
                              text="PO Compiler Pro", 
                              font=("Segoe UI", 24, "bold"),
                              fg="#1f2937",
                              bg="#f8fafc")
        title_label.pack(anchor="center")
        
        # Subtitle - centered
        subtitle_label = tk.Label(title_container, 
                                 text="Generate and manage purchase order emails with ease", 
                                 font=("Segoe UI", 10),
                                 fg="#6b7280",
                                 bg="#f8fafc")
        subtitle_label.pack(anchor="center", pady=(2, 0))
        
        # Divider line
        divider = tk.Frame(header_frame, height=1, bg="#e5e7eb")
        divider.pack(fill=tk.X, pady=(8, 0))
        
    def create_form_sections(self, parent):
        # Create a container with less padding
        form_container = tk.Frame(parent, bg="white")
        form_container.pack(fill=tk.BOTH, expand=True, padx=25, pady=15)
        
        # PO Selection Section
        self.create_po_section(form_container)
        
        # Date Selection Section
        self.create_date_section(form_container)
        
        # File Upload Section
        self.create_file_section(form_container)
        
        # Action Section
        self.create_action_section(form_container)
        
    def create_section_header(self, parent, title, subtitle=""):
        section_frame = tk.Frame(parent, bg="white")
        section_frame.pack(fill=tk.X, pady=(15, 8))
        
        title_label = tk.Label(section_frame, 
                              text=title, 
                              font=("Segoe UI", 13, "bold"),
                              fg="#1f2937",
                              bg="white")
        title_label.pack(anchor="w")
        
        if subtitle:
            subtitle_label = tk.Label(section_frame, 
                                     text=subtitle, 
                                     font=("Segoe UI", 9),
                                     fg="#6b7280",
                                     bg="white")
            subtitle_label.pack(anchor="w", pady=(1, 0))
            
        return section_frame
        
    def create_po_section(self, parent):
        self.create_section_header(parent, "Purchase Order Selection", 
                                  "Choose the company for PO compilation")
        
        po_frame = tk.Frame(parent, bg="white")
        po_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.func_dropdown = ttk.Combobox(po_frame, 
                                         values=list(retailer_modes.keys()),
                                         state="readonly", 
                                         font=("Segoe UI", 11),
                                         style='Modern.TCombobox',
                                         height=8)
        self.func_dropdown.pack(fill=tk.X)
        
        
    def create_date_section(self, parent):
        self.create_section_header(parent, "Date Selection", 
                                  "Select the date for PO processing")
        
        date_frame = tk.Frame(parent, bg="white")
        date_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Date input container
        date_input_frame = tk.Frame(date_frame, bg="white")
        date_input_frame.pack(fill=tk.X)
        
        # Day
        day_frame = tk.Frame(date_input_frame, bg="white")
        day_frame.pack(side=tk.LEFT, padx=(0, 15))
        
        tk.Label(day_frame, text="Day", font=("Segoe UI", 9, "bold"), 
                fg="#374151", bg="white").pack(anchor="w")
        
        self.day_var = tk.StringVar()
        day_dropdown = ttk.Combobox(day_frame, textvariable=self.day_var, 
                                   state="readonly", width=8,
                                   values=[f'{i:02}' for i in range(1, 32)],
                                   style='Modern.TCombobox')
        day_dropdown.pack(pady=(3, 0))
        
        # Month
        month_frame = tk.Frame(date_input_frame, bg="white")
        month_frame.pack(side=tk.LEFT, padx=(0, 15))
        
        tk.Label(month_frame, text="Month", font=("Segoe UI", 9, "bold"), 
                fg="#374151", bg="white").pack(anchor="w")
        
        self.month_var = tk.StringVar()
        month_dropdown = ttk.Combobox(month_frame, textvariable=self.month_var, 
                                     state="readonly", width=8,
                                     values=[f'{i:02}' for i in range(1, 13)],
                                     style='Modern.TCombobox')
        month_dropdown.pack(pady=(3, 0))
        
        # Year
        year_frame = tk.Frame(date_input_frame, bg="white")
        year_frame.pack(side=tk.LEFT)
        
        tk.Label(year_frame, text="Year", font=("Segoe UI", 9, "bold"), 
                fg="#374151", bg="white").pack(anchor="w")
        
        self.year_var = tk.StringVar()
        year_dropdown = ttk.Combobox(year_frame, textvariable=self.year_var, 
                                    state="readonly", width=10,
                                    values=[str(year) for year in range(2024, datetime.now().year + 5)],
                                    style='Modern.TCombobox')
        year_dropdown.pack(pady=(3, 0))
        
        # Set default values
        now = datetime.now()
        self.day_var.set(now.strftime("%d"))
        self.month_var.set(now.strftime("%m"))
        self.year_var.set(now.strftime("%Y"))
        
    def create_file_section(self, parent):
        self.create_section_header(parent, "File Upload", 
                                  "Select a file to process (optional)")
        
        file_frame = tk.Frame(parent, bg="white")
        file_frame.pack(fill=tk.X, pady=(0, 5))
        
        file_input_frame = tk.Frame(file_frame, bg="white")
        file_input_frame.pack(fill=tk.X)
        
        self.file_var = tk.StringVar()
        self.file_entry = ttk.Entry(file_input_frame, textvariable=self.file_var, 
                                   state="readonly", font=("Segoe UI", 11),
                                   style='Modern.TEntry')
        self.file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 15))
        
        upload_btn = ttk.Button(file_input_frame, text="Browse Files", 
                               command=self.upload_file,
                               style='Success.TButton')
        upload_btn.pack(side=tk.RIGHT)
        
    def create_action_section(self, parent):
        # Action section with compact spacing
        action_frame = tk.Frame(parent, bg="white")
        action_frame.pack(fill=tk.X, pady=(20, 10))
        
        # Generate button container
        button_container = tk.Frame(action_frame, bg="white")
        button_container.pack(fill=tk.X)
        
        # Generate button
        self.generate_btn = ttk.Button(button_container, 
                                      text="🚀 Generate Email", 
                                      command=self.generate_email,
                                      style='Modern.TButton')
        self.generate_btn.pack(side=tk.LEFT)
        
        # Status indicator
        self.status_label = tk.Label(button_container, 
                                    text="", 
                                    font=("Segoe UI", 20, "bold"), 
                                    bg="white")
        self.status_label.pack(side=tk.LEFT, padx=(15, 0))
        
        # Progress bar
        progress_frame = tk.Frame(action_frame, bg="white")
        progress_frame.pack(fill=tk.X, pady=(15, 0))
        
        self.progress_bar = ttk.Progressbar(progress_frame, 
                                           mode='indeterminate', 
                                           length=350,
                                           style='Modern.Horizontal.TProgressbar')
        self.progress_bar.pack()
        
        # Status text
        self.status_text = tk.Label(progress_frame, 
                                   text="Ready to generate email", 
                                   font=("Segoe UI", 9),
                                   fg="#6b7280",
                                   bg="white")
        self.status_text.pack(pady=(8, 0))
        
    def upload_file(self):
        file_path = filedialog.askopenfilename(
            title="Select File",
            filetypes=[
                ("All Files", "*.*"),
                ("Excel Files", "*.xlsx *.xls"),
                ("CSV Files", "*.csv"),
                ("Text Files", "*.txt")
            ]
        )
        if file_path:
            self.file_var.set(file_path)
            print(f"File selected: {file_path}")

    def trigger_function(self, selected_func_name, selected_date, selected_file):
        try:
            self.status_text.config(text="Processing email recipients...")
            self.logger.info("-" * 60)
            self.logger.info(f"Processing retailer: {selected_func_name}")
            self.logger.info("-" * 60)

            print(f"DEBUG: Processing {selected_func_name} for date {selected_date}")

            # ------------------ FETCH EMAILS ------------------
            recivers_emails = []
            emailControlData = sheet.get_all_records()

            for emailData in emailControlData:
                if emailData['company'].strip().upper() == selected_func_name.strip().upper():
                    emails = emailData['recivers_email'].split(',')
                    for email in emails:
                        email = email.strip()
                        if email and email not in recivers_emails:
                            recivers_emails.append(email)

            self.logger.info(f"Found {len(recivers_emails)} recipients")
            print(f"DEBUG: Found {len(recivers_emails)} email recipients")

            # ------------------ DETERMINE MODE ------------------
            mode = retailer_modes.get(selected_func_name.strip().upper())

            if mode == "REGEX":
                if selected_func_name in function_map:
                    selected_func = function_map[selected_func_name]
                else:
                    raise Exception(f"No REGEX handler found for {selected_func_name}")

            elif mode == "LLM":
                prompt_file_name = selected_func_name.lower().replace(" ", "_")

                selected_func = lambda emails, date, file: run_llm_po(
                    emails,
                    date,
                    file,
                    retailer_key=prompt_file_name,
                    retailer_name=selected_func_name
                )


            else:
                raise Exception(f"Mode not defined for {selected_func_name} in retailers sheet")

            # ------------------ EXECUTE ------------------
            self.progress_bar.start(10)
            self.status_text.config(text=f"Generating email for {selected_func_name}...")

            self.logger.info(f"Calling function for {selected_func_name} with date {selected_date}")
            print(f"DEBUG: Executing function for {selected_func_name}")

            result = selected_func(recivers_emails, selected_date, selected_file)
            self.logger.info(f"PO Processing Result: {result}")

            time.sleep(2)
            self.progress_bar.stop()
            self.status_label.config(text="✅", fg="#10b981")
            self.status_text.config(text="Email generated successfully!")

            self.logger.info(" PROCESS COMPLETED")
            self.logger.info(f"Result: {result}")
            self.logger.info("=" * 70)

            print(f"SUCCESS: Email generation completed - {result}")
            messagebox.showinfo("Success", f"{result}")

            try:
                upload_logs_to_s3()
            except Exception as e:
                print("Log upload failed:", e)


        except Exception as e:
            self.progress_bar.stop()
            self.status_label.config(text="❌", fg="#ef4444")
            self.status_text.config(text="Generation failed!")

            self.logger.error(" PROCESS FAILED")
            self.logger.error(f"Company: {selected_func_name}")
            self.logger.error(f"Error: {e}")
            self.logger.info("=" * 70)

            #print(f"ERROR: Failed to generate email - {str(e)}")
            import traceback
            print("❌ FULL ERROR TRACE:")
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed to fetch '{selected_func_name}': {e}")

            try:
                upload_logs_to_s3()
            except Exception as err:
                print("Log upload failed:", err)

    def generate_email(self):
        selected_func_name = self.func_dropdown.get()
        
        if not selected_func_name:
            messagebox.showwarning("Warning", "Please select a PO to fetch.")
            print("WARNING: No PO selected")
            return
            
        selected_date = datetime.strptime(
            f"{self.day_var.get()}-{self.month_var.get()}-{self.year_var.get()}", 
            "%d-%m-%Y"
        ).strftime("%d-%b-%Y")
        
        selected_file = self.file_var.get()

        self.logger.info("=" * 70)
        self.logger.info(f" NEW RUN STARTED")
        self.logger.info(f"Company: {selected_func_name}")
        self.logger.info(f"Date: {selected_date}")
        self.logger.info(f"File: {selected_file if selected_file else 'None'}")
        self.logger.info("=" * 70)

        print(f"DEBUG: Starting email generation process...")
        print(f"DEBUG: Company: {selected_func_name}")
        print(f"DEBUG: Date: {selected_date}")
        print(f"DEBUG: File: {selected_file if selected_file else 'None'}")
        
        self.status_label.config(text="⏳", fg="#f59e0b")
        self.status_text.config(text="Starting email generation...")
        
        threading.Thread(target=self.trigger_function, 
                        args=(selected_func_name, selected_date, selected_file)).start()
        
    def __del__(self):
        """Cleanup when application closes"""
        try:
            # Restore original stdout
            sys.stdout = self.log_capture.original_stdout
            if self.log_window and self.log_window.winfo_exists():
                self.log_window.destroy()
        except:
            pass

# Create the main window
if __name__ == "__main__":
    root = tk.Tk()
    app = ModernPOCompiler(root)
    print("Application started successfully!")
    root.mainloop()
