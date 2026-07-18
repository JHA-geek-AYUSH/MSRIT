import os
import re
from datetime import datetime

root_dir = r"z:\Hackathons\GemmaFinOS\GemmaFinOS"
exclude_dirs = {"node_modules", "venv", ".next", ".git", "__pycache__", ".vscode", "dist", "build"}

files_with_different_dates = []
files_with_dates = []

# Look for year 202x or July.
# But we specifically want to see if there is ANY date other than 18 July 2026.
# Let's search for "202", "Jul" etc.
date_regex = re.compile(r'\b(202\d|Jul|July|18)\b')

for dirpath, dirnames, filenames in os.walk(root_dir):
    dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
    for filename in filenames:
        filepath = os.path.join(dirpath, filename)
        
        try:
            mtime = os.path.getmtime(filepath)
            dt = datetime.fromtimestamp(mtime)
            # Find files not modified on 18 July 2026
            if dt.strftime("%Y-%m-%d") != "2026-07-18":
                files_with_different_dates.append((filepath, dt.strftime("%Y-%m-%d %H:%M:%S")))
        except Exception:
            pass
        
        # Search content for potential date strings
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    if date_regex.search(line):
                        files_with_dates.append((filepath, i+1, line.strip()))
        except Exception:
            pass

with open('dates_output.txt', 'w', encoding='utf-8') as out_f:
    out_f.write("Files modified on dates OTHER than 2026-07-18:\n")
    if not files_with_different_dates:
        out_f.write("None found.\n")
    for fp, dt in files_with_different_dates:
        out_f.write(f"{dt} - {fp}\n")

    out_f.write("\nFiles with potential hardcoded dates/traces:\n")
    if not files_with_dates:
        out_f.write("None found.\n")
    for fp, ln, line in files_with_dates:
        out_f.write(f"{fp}:{ln}: {line}\n")
