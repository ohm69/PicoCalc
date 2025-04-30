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
        with open(full_path) as f:
            exec(f.read(), globals())
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
                
if __name__ == "__main__":
    main_menu()