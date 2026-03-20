"""
User Profile UI Page
Handles UI for importing, viewing, and managing user profile data
"""

import tkinter as tk
from tkinter import simpledialog, messagebox, scrolledtext
from pathlib import Path
import sys

def get_colors():
    """Get Cristine color palette"""
    return {
        'bg_top': "#03060A",
        'bg_bot': "#0A1220",
        'pri': "#4FD1FF",
        'sec': "#A66CFF",
        'acc': "#52FFA8",
        'glass_bg': "#0D1B2E",
        'glass_border': "#3A5A7E",
        'text_pri': "#CBEFFF",
        'text_sec': "#7FAAC9",
        'warn': "#FFB020",
        'err': "#FF4A6E",
        'success': "#52FFA8",
        'dim': "#1B2D44",
        'dimmer': "#0D1520"
    }

C = get_colors()

class ImportDataDialog(tk.Toplevel):
    """Dialog for importing user data from another AI"""
    
    def __init__(self, parent, profile_manager):
        super().__init__(parent)
        self.title("Import Data From Another AI")
        self.geometry("700x600")
        self.configure(bg=C['bg_top'])
        self.resizable(True, True)
        
        self.profile_manager = profile_manager
        self.result = None
        
        # Make window modal
        self.transient(parent)
        self.grab_set()
        
        self._create_ui()
        self.geometry("700x600")
    
    def _create_ui(self):
        """Create the import dialog UI"""
        # Title
        title_frame = tk.Frame(self, bg=C['bg_top'], highlightbackground=C['glass_border'], highlightthickness=1)
        title_frame.pack(fill="x", padx=10, pady=10)
        tk.Label(title_frame, text="Import Personal Data", fg=C['pri'], bg=C['bg_top'], 
                font=("Courier", 12, "bold")).pack(pady=8)
        
        # Instructions
        instr_text = """1. Export your saved notes/memories/instructions from wherever you keep them
2. Paste the exported text into the box below
3. Click Import"""
        
        tk.Label(self, text=instr_text, fg=C['text_sec'], bg=C['bg_top'], 
                font=("Courier", 9), justify="left").pack(padx=10, pady=(5, 10), anchor="w")
        
        # Prompt section
        prompt_label = tk.Label(self, text="▼ OPTIONAL TEMPLATE (click to copy)", fg=C['acc'], bg=C['bg_top'], 
                               font=("Courier", 9, "bold"), cursor="hand2")
        prompt_label.pack(padx=10, pady=(10, 0), anchor="w")
        
        prompt_frame = tk.Frame(self, bg=C['glass_bg'], highlightbackground=C['glass_border'], highlightthickness=1)
        prompt_frame.pack(padx=10, pady=(5, 10), fill="both", expand=False)
        
        self.prompt_text = scrolledtext.ScrolledText(prompt_frame, height=8, width=80, 
                                                     fg=C['text_pri'], bg=C['glass_bg'], 
                                                     insertbackground=C['text_pri'], borderwidth=0,
                                                     font=("Courier", 8))
        self.prompt_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.prompt_text.insert("1.0", self.profile_manager.get_export_prompt())
        self.prompt_text.configure(state="disabled")
        
        copy_btn = tk.Button(self, text="📋 COPY PROMPT", command=self._copy_prompt,
                           bg=C['dim'], fg=C['pri'], font=("Courier", 9, "bold"),
                           borderwidth=0, padx=10, pady=5)
        copy_btn.pack(pady=(0, 10))
        
        # Paste data section
        tk.Label(self, text="▼ PASTE RESULT HERE", fg=C['acc'], bg=C['bg_top'], 
                font=("Courier", 9, "bold")).pack(padx=10, pady=(10, 5), anchor="w")
        
        paste_frame = tk.Frame(self, bg=C['glass_bg'], highlightbackground=C['glass_border'], highlightthickness=1)
        paste_frame.pack(padx=10, pady=(0, 10), fill="both", expand=True)
        
        self.paste_text = scrolledtext.ScrolledText(paste_frame, height=12, width=80,
                                                    fg=C['text_pri'], bg=C['glass_bg'],
                                                    insertbackground=C['pri'], borderwidth=0,
                                                    font=("Courier", 8))
        self.paste_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.paste_text.focus()
        
        # Buttons
        button_frame = tk.Frame(self, bg=C['bg_top'])
        button_frame.pack(fill="x", padx=10, pady=10)
        
        tk.Button(button_frame, text="IMPORT", command=self._import_data,
                bg=C['dim'], fg=C['success'], font=("Courier", 10, "bold"),
                borderwidth=0, padx=15, pady=6).pack(side="left", padx=5)
        
        tk.Button(button_frame, text="CANCEL", command=self.destroy,
                bg=C['dim'], fg=C['text_sec'], font=("Courier", 10, "bold"),
                borderwidth=0, padx=15, pady=6).pack(side="left", padx=5)
    
    def _copy_prompt(self):
        """Copy export prompt to clipboard"""
        try:
            self.clipboard_clear()
            self.clipboard_append(self.profile_manager.get_export_prompt())
            messagebox.showinfo("Copied", "Export prompt copied to clipboard!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to copy: {str(e)}")
    
    def _import_data(self):
        """Import pasted data"""
        data = self.paste_text.get("1.0", "end-1c").strip()
        
        if not data:
            messagebox.showwarning("Empty", "Please paste the exported data first")
            return
        
        result = self.profile_manager.import_data(data)
        
        if result['success']:
            summary = result.get('summary', '')
            messagebox.showinfo("Success", f"Data imported successfully!\n\n{summary}")
            self.result = result
            self.destroy()
        else:
            errors = "\n".join(result.get('errors', ['Unknown error']))
            messagebox.showerror("Import Failed", f"Error importing data:\n\n{errors}")


class DataViewerWindow(tk.Toplevel):
    """Window to view stored user profile data"""
    
    def __init__(self, parent, profile_manager):
        super().__init__(parent)
        self.title("View My Stored Data")
        self.geometry("700x600")
        self.configure(bg=C['bg_top'])
        self.resizable(True, True)
        
        self.profile_manager = profile_manager
        self.collapsed = {}  # Track which sections are collapsed
        
        self.transient(parent)
        self.grab_set()
        
        self._create_ui()
    
    def _create_ui(self):
        """Create the data viewer UI"""
        # Title
        title_frame = tk.Frame(self, bg=C['bg_top'], highlightbackground=C['glass_border'], highlightthickness=1)
        title_frame.pack(fill="x", padx=10, pady=10)
        tk.Label(title_frame, text="Your Stored Personal Data", fg=C['pri'], bg=C['bg_top'],
                font=("Courier", 12, "bold")).pack(pady=8)
        
        # Main content frame with scrollbar
        content_frame = tk.Frame(self, bg=C['bg_top'])
        content_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        canvas = tk.Canvas(content_frame, bg=C['bg_top'], highlightthickness=0)
        scrollbar = tk.Scrollbar(content_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=C['bg_top'])
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Create collapsible sections
        profile = self.profile_manager.get_profile()
        for category in ['instructions', 'identity', 'career', 'projects', 'preferences']:
            self.collapsed[category] = False
            entries = profile.get(category, [])
            self._create_section(scrollable_frame, category, entries)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Buttons
        button_frame = tk.Frame(self, bg=C['bg_top'])
        button_frame.pack(fill="x", padx=10, pady=10)
        
        tk.Button(button_frame, text="DELETE ALL DATA", command=self._confirm_delete_all,
                bg=C['dim'], fg=C['err'], font=("Courier", 10, "bold"),
                borderwidth=0, padx=15, pady=6).pack(side="left", padx=5)
        
        tk.Button(button_frame, text="CLOSE", command=self.destroy,
                bg=C['dim'], fg=C['text_sec'], font=("Courier", 10, "bold"),
                borderwidth=0, padx=15, pady=6).pack(side="left", padx=5)
    
    def _create_section(self, parent, category, entries):
        """Create a collapsible section for a category"""
        section_frame = tk.Frame(parent, bg=C['bg_top'])
        section_frame.pack(fill="x", pady=(10, 0))
        
        # Header with expand/collapse toggle
        header_frame = tk.Frame(section_frame, bg=C['glass_bg'], highlightbackground=C['glass_border'], 
                               highlightthickness=1, cursor="hand2")
        header_frame.pack(fill="x")
        
        header_label = tk.Label(header_frame, text=f"▶ {category.upper()} ({len(entries)})",
                               fg=C['pri'], bg=C['glass_bg'], font=("Courier", 10, "bold"),
                               padx=10, pady=6)
        header_label.pack(fill="x")
        
        # Content frame (initially hidden)
        content_frame = tk.Frame(section_frame, bg=C['glass_bg'])
        
        def toggle(cat=category, cf=content_frame, lbl=header_label):
            self.collapsed[cat] = not self.collapsed[cat]
            if self.collapsed[cat]:
                cf.pack_forget()
                lbl.configure(text=f"▶ {cat.upper()} ({len(entries)})")
            else:
                cf.pack(fill="x")
                lbl.configure(text=f"▼ {cat.upper()} ({len(entries)})")
        
        header_label.bind("<Button-1>", lambda e: toggle())
        header_frame.bind("<Button-1>", lambda e: toggle())
        
        # Entries
        if entries:
            for idx, entry in enumerate(entries):
                date = entry.get('date', 'unknown')
                content = entry.get('content', '')
                
                entry_frame = tk.Frame(content_frame, bg=C['dimmer'], 
                                      highlightbackground=C['glass_border'], highlightthickness=1)
                entry_frame.pack(fill="x", padx=5, pady=5)
                
                # Entry content
                text_label = tk.Label(entry_frame, text=f"[{date}] - {content}",
                                     fg=C['text_pri'], bg=C['dimmer'], font=("Courier", 9),
                                     wraplength=650, justify="left", padx=8, pady=6)
                text_label.pack(fill="x", anchor="w")
                
                # Delete button
                del_btn = tk.Button(entry_frame, text="✕ DELETE",
                                   command=lambda cat=category, i=idx: self._confirm_delete_entry(cat, i),
                                   bg=C['dim'], fg=C['warn'], font=("Courier", 8),
                                   borderwidth=0, padx=8, pady=2)
                del_btn.pack(side="right", padx=3, pady=3)
        else:
            empty_label = tk.Label(content_frame, text="(empty)",
                                  fg=C['text_sec'], bg=C['glass_bg'], font=("Courier", 9),
                                  padx=10, pady=6)
            empty_label.pack(fill="x")
        
        content_frame.pack(fill="x")
        
        # Category delete button
        cat_del_btn = tk.Button(section_frame, text=f"DELETE {category.upper()} CATEGORY",
                               command=lambda cat=category: self._confirm_delete_category(cat),
                               bg=C['dim'], fg=C['err'], font=("Courier", 8, "bold"),
                               borderwidth=0, padx=8, pady=4)
        cat_del_btn.pack(pady=(0, 5))
    
    def _confirm_delete_entry(self, category, index):
        """Confirm deletion of a single entry"""
        if messagebox.askyesno("Delete Entry", "Are you sure you want to delete this entry?"):
            if self.profile_manager.delete_entry(category, index):
                messagebox.showinfo("Deleted", "Entry deleted successfully")
                self.destroy()
                # Reopen viewer to refresh
                parent = self.master
                self.__class__(parent, self.profile_manager)
            else:
                messagebox.showerror("Error", "Failed to delete entry")
    
    def _confirm_delete_category(self, category):
        """Confirm deletion of entire category"""
        if messagebox.askyesno("Delete Category", 
                              f"Are you sure you want to delete all {category} entries?"):
            if self.profile_manager.delete_category(category):
                messagebox.showinfo("Deleted", f"{category.capitalize()} category cleared")
                self.destroy()
                # Reopen viewer to refresh
                parent = self.master
                self.__class__(parent, self.profile_manager)
            else:
                messagebox.showerror("Error", "Failed to delete category")
    
    def _confirm_delete_all(self):
        """Confirm deletion of all data"""
        if messagebox.askyesno("Delete All Data", 
                              "⚠ Are you sure you want to delete ALL stored personal data?\n\nThis cannot be undone.", 
                              icon=messagebox.WARNING):
            if self.profile_manager.delete_all():
                messagebox.showinfo("Deleted", "All personal data has been deleted")
                self.destroy()
                # Reopen viewer to refresh
                parent = self.master
                self.__class__(parent, self.profile_manager)
            else:
                messagebox.showerror("Error", "Failed to delete data")


def show_import_dialog(parent, profile_manager):
    """Show import dialog"""
    dialog = ImportDataDialog(parent, profile_manager)
    parent.wait_window(dialog)
    return dialog.result


def show_data_viewer(parent, profile_manager):
    """Show data viewer window"""
    DataViewerWindow(parent, profile_manager)
