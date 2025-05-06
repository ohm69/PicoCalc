import sys
import gc

try:
    from picocalc import PicoKeyboard
    kbd = PicoKeyboard()
except:
    kbd = None

def flush_stdout_stderr():
    count = 0
    for stream in [sys.stdout, sys.stderr]:
        if hasattr(stream, "flush") and callable(stream.flush):
            try:
                stream.flush()
                count += 1
            except:
                pass
    return count

def flush_file_handles():
    count = 0
    visited = set()
    for name in dir(sys.modules):
        module = sys.modules.get(name)
        if module is None:
            continue
        for attr_name in dir(module):
            try:
                attr = getattr(module, attr_name)
                if id(attr) not in visited and hasattr(attr, "flush") and callable(attr.flush):
                    attr.flush()
                    visited.add(id(attr))
                    count += 1
            except:
                pass
    return count

def list_modules(exclude=("os", "sys", "gc", "micropython")):
    return sorted(name for name in sys.modules if name not in exclude and not name.startswith("micropython"))

def flush_selected_modules(selected):
    count = 0
    for name in selected:
        if name in sys.modules:
            sys.modules.pop(name, None)
            count += 1
    return count

def show_menu():
    options = [
        "1. Flush stdout/stderr",
        "2. Flush file handles",
        "3. Select modules to flush",
        "4. Full cleanup",
        "5. Exit"
    ]
    print("\n=== Flush Menu ===")
    for opt in options:
        print(opt)
    return input("Select 1-5: ").strip()

def select_modules_to_flush():
    mods = list_modules()
    if not mods:
        print("No flushable modules.")
        return []
    print("\nModules:")
    for i, mod in enumerate(mods):
        print(f"{i + 1}: {mod}")
    entry = input("Select (e.g. 1,3,5): ")
    indices = entry.replace(" ", "").split(",")
    selected = []
    for idx in indices:
        try:
            i = int(idx) - 1
            if 0 <= i < len(mods):
                selected.append(mods[i])
        except:
            pass
    return selected

def run_flush_menu():
    while True:
        choice = show_menu()
        if choice == "1":
            count = flush_stdout_stderr()
            print(f"Flushed {count} streams.")
        elif choice == "2":
            count = flush_file_handles()
            print(f"Flushed {count} file handles.")
        elif choice == "3":
            selected = select_modules_to_flush()
            count = flush_selected_modules(selected)
            print(f"Flushed {count} modules.")
        elif choice == "4":
            total = flush_stdout_stderr() + flush_file_handles() + flush_selected_modules(list_modules())
            print(f"Full cleanup done. {total} items flushed.")
        elif choice == "5":
            print("Exit.")
            break
        else:
            print("Invalid choice.")
        gc.collect()
        print(f"GC done. Free RAM: {gc.mem_free()} bytes")
        input("Press Enter...")

if __name__ == "__main__":
    run_flush_menu()