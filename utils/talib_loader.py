import os
import sys
import subprocess
import warnings
import importlib.util

print("--- Running talib_loader.py ---")

# --- Configuration ---
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
# !! Adjust path if your structure is different !!
INCLUDE_DIR = os.path.join(PROJECT_ROOT, 'lib', 'talib', 'include') # Dir containing ta_defs.h
LIB_DIR = os.path.join(PROJECT_ROOT, 'lib', 'talib', 'lib')         # Dir containing libta_lib.so.0
LIB_FILE_CHECK = os.path.join(LIB_DIR, 'libta_lib.so.0')          # Specific file to check
HEADER_FILE_CHECK = os.path.join(INCLUDE_DIR, 'ta_defs.h')        # Specific header to check

# --- Check Pre-compiled Library and Headers ---
if not os.path.exists(LIB_FILE_CHECK):
    raise FileNotFoundError(f"CRITICAL: Pre-compiled TA-Lib library not found at {LIB_FILE_CHECK}.")
if not os.path.exists(HEADER_FILE_CHECK):
     raise FileNotFoundError(f"CRITICAL: Pre-compiled TA-Lib header not found at {HEADER_FILE_CHECK}.")

print(f"Found pre-compiled TA-Lib library: {LIB_FILE_CHECK}")
print(f"Found pre-compiled TA-Lib include: {INCLUDE_DIR}")


# --- Set Environment Variables ---
# Set LD_LIBRARY_PATH for runtime loading
original_ld_path = os.environ.get('LD_LIBRARY_PATH', '')
if LIB_DIR not in original_ld_path.split(os.pathsep):
    print(f"Adding {LIB_DIR} to LD_LIBRARY_PATH")
    os.environ['LD_LIBRARY_PATH'] = LIB_DIR + (os.pathsep + original_ld_path if original_ld_path else '')

# Set TA_* paths for the build process (used by pip install TA-Lib)
os.environ['TA_LIBRARY_PATH'] = LIB_DIR
os.environ['TA_INCLUDE_PATH'] = INCLUDE_DIR
print(f"Set TA_LIBRARY_PATH={os.environ['TA_LIBRARY_PATH']}")
print(f"Set TA_INCLUDE_PATH={os.environ['TA_INCLUDE_PATH']}")
print(f"Current LD_LIBRARY_PATH={os.environ.get('LD_LIBRARY_PATH')}")


# --- Check if TA-Lib Python Wrapper is Installed and Install if Missing ---
talib_module = None
try:
    # Try importing first - it might exist from a previous run
    import talib
    print(f"TA-Lib Python wrapper already found. Version: {getattr(talib, '__version__', 'unknown')}")
    talib_module = talib
except ImportError:
    # ****** THIS BLOCK RUNS IF 'import talib' FAILS ******
    print("TA-Lib Python wrapper not found. Attempting installation using pip...")
    try:
        # Ensure numpy is installed first (build dependency for TA-Lib)
        print("Ensuring numpy is installed...")
        # Use subprocess.run with check=True to ensure it succeeds or raises error
        subprocess.run([sys.executable, "-m", "pip", "install", "numpy"], check=True, capture_output=True, text=True)
        print("Numpy installed or already present.")

        # Use pip to install the TA-Lib wrapper, relying on TA_* env vars set above
        pip_command = [
            sys.executable, "-m", "pip", "install", "--no-cache-dir",
            "TA-Lib" # Install the package from PyPI
        ]
        print(f"Running command: {' '.join(pip_command)}")
        # Pass the current environment which includes our TA_* vars
        result = subprocess.run(pip_command, check=True, capture_output=True, text=True, env=os.environ.copy())
        print("pip install stdout:\n", result.stdout)
        if result.stderr: # Only print stderr if it's not empty
             print("pip install stderr:\n", result.stderr, file=sys.stderr)
        print("TA-Lib Python wrapper installed successfully via pip.")

        # Import *after* successful installation
        import talib
        talib_module = talib

    # Catch potential errors during the pip install process
    except subprocess.CalledProcessError as e:
        print(f"ERROR: pip install TA-Lib failed.", file=sys.stderr)
        print(f"Return Code: {e.returncode}", file=sys.stderr)
        # Print details helpful for debugging the build failure
        print(f"Environment Variables during failed pip install:", file=sys.stderr)
        print(f"  TA_LIBRARY_PATH={os.environ.get('TA_LIBRARY_PATH')}", file=sys.stderr)
        print(f"  TA_INCLUDE_PATH={os.environ.get('TA_INCLUDE_PATH')}", file=sys.stderr)
        print(f"  LD_LIBRARY_PATH={os.environ.get('LD_LIBRARY_PATH')}", file=sys.stderr)
        print(f"\n--- pip stdout ---\n{e.stdout}\n------------------", file=sys.stderr)
        print(f"\n--- pip stderr ---\n{e.stderr}\n------------------", file=sys.stderr)
        raise RuntimeError("Failed to install TA-Lib Python wrapper.") from e
    except ImportError as e_import:
         print(f"ERROR: Failed to import talib even after apparent successful install.", file=sys.stderr)
         raise e_import
    except Exception as e_generic:
         print(f"ERROR: An unexpected error occurred during TA-Lib installation: {type(e_generic).__name__}", file=sys.stderr)
         raise e_generic


# --- Final Check ---
if talib_module is None:
     # This should ideally not be reached if the logic above is correct
     raise ImportError("Failed to load or install the TA-Lib Python module.")

print(f"Successfully loaded TA-Lib. Version: {getattr(talib_module, '__version__', 'unknown')}")
print("--- Finished talib_loader.py ---")