# flush.py

import sys
import gc

def flush():
    """
    Safely flush all flushable objects in MicroPython environment.
    
    Returns:
        int: Number of objects flushed successfully
    """
    flushed_count = 0
    
    # Set to track already visited objects to prevent recursion
    visited = set()
    
    # Standard streams first
    for stream in [sys.stdout, sys.stderr]:
        if hasattr(stream, 'flush') and callable(stream.flush):
            try:
                stream.flush()
                flushed_count += 1
            except Exception:
                pass
    
    # Simple approach: just flush basic file-like objects
    # This avoids the recursion issue that happened with module inspection
    for name in dir(sys.modules):
        try:
            module = sys.modules[name]
            # Skip modules that are None
            if module is None:
                continue
                
            # Try to find module-level file objects
            for attr_name in dir(module):
                # Skip private attributes and our own function
                if attr_name.startswith('_') or (module.__name__ == 'flush' and attr_name == 'flush'):
                    continue
                    
                try:
                    # Try to get file-like objects only
                    attr = getattr(module, attr_name)
                    if id(attr) not in visited and hasattr(attr, 'flush') and callable(attr.flush):
                        attr.flush()
                        visited.add(id(attr))
                        flushed_count += 1
                except Exception:
                    pass
        except Exception:
            pass
    
    # Force garbage collection
    gc.collect()
    
    return flushed_count