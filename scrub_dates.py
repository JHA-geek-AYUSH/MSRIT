import os
import re
from datetime import datetime, timedelta
import ctypes
from ctypes import wintypes

root_dir = r"z:\Hackathons\GemmaFinOS\GemmaFinOS"

# 1. Text Replacements
files_to_check = [
    ".md", ".tsx", ".ts", ".py", ".json", ".txt", ".sh", ".bat"
]

def replace_in_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        new_content = content
        
        # Specific replacements requested
        new_content = re.sub(r'DPDP 18 July 2026', 'DPDP 18 July 2026', new_content)
        new_content = re.sub(r'18 July 2026', '18 July 2026', new_content)
        new_content = re.sub(r'Hackathon 18 July 2026', 'Hackathon 18 July 2026', new_content)
        
        if 'design.md' in filepath:
            new_content = new_content.replace('date(2024,1,1)', 'date(2026,7,18)')
            new_content = new_content.replace('date(2024,1,2)', 'date(2026,7,18)')
            
        if new_content != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Updated text in {filepath}")
    except Exception as e:
        pass

print("Starting text replacements...")
for root, dirs, files in os.walk(root_dir):
    if '.git' in dirs:
        dirs.remove('.git')
    for file in files:
        if any(file.endswith(ext) for ext in files_to_check):
            filepath = os.path.join(root, file)
            replace_in_file(filepath)

# 2. Hierarchical Timestamp Rewrite
print("\nStarting timestamp rewrites...")
start_time = datetime(2026, 7, 18, 10, 15, 0)
current_time = start_time
# we will use an increment of 1 millisecond for each file/dir to make it hierarchical and sequential without spilling to the next day
time_increment = timedelta(milliseconds=1)

kernel32 = ctypes.windll.kernel32

def set_file_times(filepath, timestamp):
    epoch_as_filetime = 116444736000000000
    filetime = int(timestamp * 10000000) + epoch_as_filetime
    
    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD),
                    ("dwHighDateTime", wintypes.DWORD)]
                    
    ft = FILETIME(filetime & 0xFFFFFFFF, filetime >> 32)
    
    # FILE_WRITE_ATTRIBUTES = 0x0100
    # OPEN_EXISTING = 3
    # FILE_FLAG_BACKUP_SEMANTICS = 0x02000000 (needed for directory operations)
    handle = kernel32.CreateFileW(
        str(filepath), 
        0x0100, 
        3, 
        None, 
        3, 
        0x02000000, 
        None
    )
    if handle != -1:
        # Set Creation, Access, and Write times all to the same value
        kernel32.SetFileTime(handle, ctypes.byref(ft), ctypes.byref(ft), ctypes.byref(ft))
        kernel32.CloseHandle(handle)
    else:
        # fallback to os.utime if handle fails
        try:
            os.utime(filepath, (timestamp, timestamp))
        except:
            pass

# Process bottom-up (topdown=False) so that updating a file doesn't override the parent directory's time 
# after we've set the parent directory's time.
for root, dirs, files in os.walk(root_dir, topdown=False):
    if '.git' in root:
        continue
        
    for file in files:
        filepath = os.path.join(root, file)
        mtime = current_time.timestamp()
        set_file_times(filepath, mtime)
        current_time += time_increment
            
    # Then touch the directory itself
    mtime = current_time.timestamp()
    set_file_times(root, mtime)
    current_time += time_increment

print(f"Finished! Final timestamp applied was {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
