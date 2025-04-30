import os
import sys

# Clear cached module if needed
sys.modules.pop("mkdir", None)

def mkdir(path):
    """Create a directory if it doesn't already exist."""
    # Check if SD card is mounted
    try:
        if "sd" in os.listdir("/"):
            print("✅ SD card found")
        else:
            print("⚠️ /sd not found. Is the SD card inserted and mounted?")
            return
    except Exception as e:
        print(f"⚠️ Failed checking root filesystem: {e}")
        return

    # Normalize path
    if not path.startswith("/sd/"):
        path = "/sd/" + path
    path = path.rstrip("/")  # Remove trailing slash if any

    # Check if directory already exists
    parent_path = "/".join(path.split("/")[:-1])
    dir_name = path.split("/")[-1]
    
    try:
        entries = os.listdir(parent_path)
        if dir_name in entries:
            print(f"📂 {path} already exists.")
        else:
            try:
                os.mkdir(path)
                print(f"✅ Created {path} successfully!")
            except OSError as e:
                print(f"⚠️ Error creating {path}: {e}")
    except OSError as e:
        print(f"⚠️ Error listing {parent_path}: {e}")

# Run example (comment out if using import)
# mkdir("samples")  # This would create /sd/samples

# Cleanup
sys.modules.pop("mkdir", None)

