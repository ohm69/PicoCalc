import os
import sys
import gc

def find_py_files(base_path="/sd"):
    py_files = []
    try:
        for entry in os.listdir(base_path):
            full_path = f"{base_path}/{entry}"
            try:
                mode = os.stat(full_path)[0]
                if mode & 0x4000:  # Directory
                    sub_files = find_py_files(full_path)
                    py_files.extend(sub_files)
                elif entry.endswith(".py"):
                    relative_path = full_path[len("/sd/"):-3]  # remove /sd/ and .py
                    py_files.append(relative_path)
            except Exception as e:
                print(f"⚠️ Error reading {full_path}: {e}")
    except Exception as e:
        print(f"⚠️ Error listing {base_path}: {e}")
    return py_files

def run_script(script_path, base_path="/sd"):
    try:
        full_path = f"{base_path}/{script_path}.py"
        
        # First, try to load the script content
        with open(full_path) as f:
            script_content = f.read()
        
        # Create a new namespace for running the script
        script_globals = {
            '__name__': '__main__',
            '__file__': full_path,
        }
        
        # Add standard modules to the namespace
        for module_name in ['os', 'sys', 'gc']:
            if module_name in globals():
                script_globals[module_name] = globals()[module_name]
        
        # Execute the script in the new namespace
        exec(script_content, script_globals)
        
        # If the script has a main_menu function and it wasn't called by the script itself
        # (which might happen with guard statements), call it
        if 'main_menu' in script_globals and callable(script_globals['main_menu']):
            if 'main_executed' not in script_globals or not script_globals['main_executed']:
                print("🔄 No entry point called, executing main_menu()...")
                script_globals['main_menu']()
                script_globals['main_executed'] = True
                
    except Exception as e:
        print(f"❌ Failed running {script_path}: {e}")

def flush_modules(exclude=("os", "sys", "gc")):
    flushed = []
    for name in list(sys.modules):
        if name not in exclude and not name.startswith("micropython"):
            sys.modules.pop(name, None)
            flushed.append(name)
    print(f"🧹 Flushed: {', '.join(flushed)}")

def show_memory():
    gc.collect()
    print(f"RAM Free: {gc.mem_free()} bytes")
    print(f"RAM Used: {gc.mem_alloc()} bytes")
    
    # Add storage space information
    try:
        # Get storage info for /sd
        stat = os.statvfs('/sd')
        block_size = stat[0]  # f_bsize - file system block size
        total_blocks = stat[2]  # f_blocks - total blocks in the filesystem
        free_blocks = stat[3]  # f_bfree - free blocks
        
        # Calculate total and free space in bytes
        total_space = block_size * total_blocks
        free_space = block_size * free_blocks
        used_space = total_space - free_space
        
        # Convert to more readable format (KB, MB)
        def format_bytes(bytes_val):
            if bytes_val >= 1024 * 1024:
                return f"{bytes_val / (1024 * 1024):.2f} MB"
            elif bytes_val >= 1024:
                return f"{bytes_val / 1024:.2f} KB"
            else:
                return f"{bytes_val} bytes"
        
        print("\nStorage on /sd:")
        print(f"Total: {format_bytes(total_space)}")
        print(f"Used:  {format_bytes(used_space)}")
        print(f"Free:  {format_bytes(free_space)}")
        print(f"Usage: {used_space / total_space * 100:.1f}%")
    except Exception as e:
        print(f"⚠️ Error getting storage info: {e}")

def main_menu():
    while True:
        scripts = find_py_files()
        print("\n=== PicoCalc Main Menu ===")
        for i, name in enumerate(scripts):
            print(f"{i + 1}: Run {name}")
        
        print("X: Exit to prompt")
        print("R: Reload menu")
        print("F: Flush & reload modules")
        print("M: Memory status")
        choice = input("\nEnter choice: ").strip().lower()
        if choice == "x":
            print("👋 Exiting to prompt.")
            return
        elif choice == "r":
            print("🔁 Reloading menu...")
            continue
        elif choice == "f":
            flush_modules()
            continue
        elif choice == "m":
            show_memory()
            continue
        else:
            try:
                index = int(choice) - 1
                if 0 <= index < len(scripts):
                    print(f"\n▶️ Running {scripts[index]}...\n")
                    run_script(scripts[index])
                    input("\n✅ Done. Press Enter to return to menu...")
                else:
                    print("❌ Invalid selection.")
            except ValueError:
                print("❌ Invalid input. Use number or option letter.")
                
# This helper variable will let us know if the main entry point was executed
main_executed = False

def check_run_main():
    """Helper function to run main_menu if this is the main script"""
    global main_executed
    if __name__ == "__main__" and not main_executed:
        main_menu()
        main_executed = True

# Two ways to run this script:
# 1. With guard statement
if __name__ == "__main__":
    main_menu()
    main_executed = True

# 2. Without guard statement (will only run if not already executed by guard)
check_run_main()