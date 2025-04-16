import os
import sys
import ctypes
import importlib.util
import warnings

# Get the project root path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Set up paths to the pre-compiled library
lib_path = os.path.join(project_root, 'lib', 'talib', 'lib')
lib_file = os.path.join(lib_path, 'libta_lib.so.0')

# Check if library exists
if not os.path.exists(lib_file):
    raise FileNotFoundError(f"Pre-compiled TA-Lib not found at {lib_file}")

print(f"Found pre-compiled TA-Lib at: {lib_file}")

# Preload the library
try:
    ctypes.cdll.LoadLibrary(lib_file)
    print("Successfully pre-loaded TA-Lib library")
except Exception as e:
    print(f"Warning: Failed to preload library: {e}")

# Add the library path to LD_LIBRARY_PATH
os.environ['LD_LIBRARY_PATH'] = lib_path + os.pathsep + os.environ.get('LD_LIBRARY_PATH', '')

# Check if talib is already installed
try:
    import talib
    print(f"Using existing TA-Lib installation: {getattr(talib, '__version__', 'unknown')}")
except ImportError:
    # Handle the case where we need to tell Python how to find talib
    # This is a simplified direct approach that bypasses pip install
    warnings.warn(
        "TA-Lib module not found. Make sure it's installed. " 
        "If you're on Streamlit Cloud, add 'TA-Lib' to your requirements.txt after "
        "the deployment has the pre-compiled library available."
    )
    raise

# Return the module
talib_module = talib