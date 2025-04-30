"""
checksd.py - Custom implementation of the checksd function for PicoCalc
This module provides a replacement for the missing checksd function in picocalc_system
"""

import os
import time

def checksd():
    """
    Check if SD card is properly initialized and mounted.
    Returns a tuple: (status, message)
    - status: Boolean indicating if SD card is mounted
    - message: String with details about SD card status
    """
    try:
        # Check if /sd directory exists and is accessible
        contents = os.listdir('/sd')
        # Count files and get total size
        file_count = 0
        total_size = 0
        
        for file in contents:
            try:
                file_path = '/sd/' + file
                stat = os.stat(file_path)
                if stat[0] & 0x8000:  # Check if it's a file (not a directory)
                    file_count += 1
                    total_size += stat[6]  # Size is at index 6
            except:
                # Skip files with errors
                pass
                
        # Format size to human-readable
        size_str = human_readable_size(total_size)
        
        msg = f"SD OK: {file_count} files, {size_str}"
        return True, msg
    except OSError:
        return False, "SD card not mounted or initialized"
    except Exception as e:
        return False, f"Error checking SD: {str(e)}"

def human_readable_size(size):
    """Convert size in bytes to human-readable format (KB, MB, etc.)"""
    suffixes = ['B', 'KB', 'MB', 'GB']
    suffix_index = 0
    value = size
    
    while value >= 1024 and suffix_index < len(suffixes) - 1:
        suffix_index += 1
        value /= 1024.0
    
    if suffix_index == 0:
        return f"{value} {suffixes[suffix_index]}"
    else:
        return f"{value:.1f} {suffixes[suffix_index]}"

# If this module is used directly, provide an easy way to test
if __name__ == "__main__":
    status, message = checksd()
    print(f"SD Card Status: {status}")
    print(f"Message: {message}")
