import os
import sys
import warnings

print("--- Running talib_loader.py ---")

# Get the project root path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Set up path to the pre-compiled library
lib_path = os.path.join(project_root, 'lib', 'talib', 'lib')
lib_file = os.path.join(lib_path, 'libta_lib.so.0') # Check for the specific file

# Check if library exists
if not os.path.exists(lib_file):
    # If the precompiled lib isn't found, we cannot proceed.
    # This indicates an issue with the repository structure or file presence.
    raise FileNotFoundError(f"CRITICAL: Pre-compiled TA-Lib shared object not found at {lib_file}. Ensure it's committed to the repository.")
else:
    print(f"Found pre-compiled TA-Lib shared object: {lib_file}")

# Add the library path to LD_LIBRARY_PATH *before* importing talib
# This ensures the Python wrapper finds our C library
original_ld_path = os.environ.get('LD_LIBRARY_PATH', '')
if lib_path not in original_ld_path.split(os.pathsep):
    print(f"Adding {lib_path} to LD_LIBRARY_PATH")
    os.environ['LD_LIBRARY_PATH'] = lib_path + (os.pathsep + original_ld_path if original_ld_path else '')
else:
    print(f"LD_LIBRARY_PATH already contains {lib_path}")

# Now, try importing talib (which should have been installed via requirements.txt)
try:
    import talib
    print(f"Successfully imported TA-Lib (presumably using pre-compiled C library). Version: {getattr(talib, '__version__', 'unknown')}")
    # Assign the module so it can be imported by app.py
    talib_module = talib
except ImportError as e:
    print(f"ERROR: Failed to import talib even after setting LD_LIBRARY_PATH.", file=sys.stderr)
    print(f"Ensure 'TA-Lib' is in requirements.txt and system packages (cmake, libssl-dev) are in packages.txt.", file=sys.stderr)
    print(f"Current LD_LIBRARY_PATH: {os.environ.get('LD_LIBRARY_PATH')}", file=sys.stderr)
    raise ImportError("Could not import the TA-Lib Python wrapper.") from e

print("--- Finished talib_loader.py ---")