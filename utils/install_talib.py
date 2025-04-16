import os
import sys
import subprocess
import shutil
import time
import traceback

# --- Configuration ---
# Use a custom installation prefix that the current user has write access to
# Instead of sys.prefix (/home/adminuser/venv) which we can't write to
CUSTOM_PREFIX = "/tmp/talib_install"  # Use /tmp which appuser can write to
INSTALL_PREFIX = CUSTOM_PREFIX
print(f"INFO: Using custom installation prefix: {INSTALL_PREFIX}")

TARBALL_NAME = "ta-lib-0.6.4-src.tar.gz"
EXTRACTED_DIR_NAME = "ta-lib-0.6.4"

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# If tarball is in the *parent* directory of this script (e.g., script is in utils/, tarball in root)
TARBALL_PATH_SRC = os.path.abspath(os.path.join(_SCRIPT_DIR, '..', TARBALL_NAME))
# If tarball is in the *same* directory as this script
# TARBALL_PATH_SRC = os.path.join(_SCRIPT_DIR, TARBALL_NAME)

TARBALL_PATH_TMP = f"/tmp/{TARBALL_NAME}"
EXTRACTED_DIR_TMP = f"/tmp/{EXTRACTED_DIR_NAME}"

# Define custom installation paths
COMPILED_LIB_DIR = os.path.join(INSTALL_PREFIX, "lib")
COMPILED_INCLUDE_DIR = os.path.join(INSTALL_PREFIX, "include")
COMPILED_LIB_PATH_CHECK = os.path.join(COMPILED_LIB_DIR, "libta_lib.so.0")

PYTHON_WRAPPER_VERSION = "TA-Lib"

_INSTALL_LOCK_FILE = "/tmp/talib_install.lock"

def _run_command(cmd, cwd=None, error_message="Command failed", check=True):
    """Helper function to run subprocess commands, print output, and handle errors."""
    print(f"--> Running command: {' '.join(cmd)}" + (f" in '{cwd}'" if cwd else ""))
    try:
        env = os.environ.copy()
        # Add the custom lib path to LD_LIBRARY_PATH so pip can find it
        if COMPILED_LIB_DIR:
            env['LD_LIBRARY_PATH'] = COMPILED_LIB_DIR + os.pathsep + env.get('LD_LIBRARY_PATH', '')
        
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False, env=env)

        print(f"  --- stdout ({len(result.stdout)} bytes) ---:\n{result.stdout.strip()}\n  --------------")
        print(f"  --- stderr ({len(result.stderr)} bytes) ---:\n{result.stderr.strip()}\n  --------------", file=sys.stderr)

        if check and result.returncode != 0:
            print(f"ERROR: {error_message}. Exit code: {result.returncode}", file=sys.stderr)
            raise subprocess.CalledProcessError(result.returncode, cmd, output=result.stdout, stderr=result.stderr)
        elif not check and result.returncode != 0:
             print(f"WARN: Command finished with non-zero exit code ({result.returncode}) but check=False.", file=sys.stderr)

        print(f"<-- Command finished: {' '.join(cmd)} (Exit Code: {result.returncode})")
        return result

    except FileNotFoundError as e:
        print(f"ERROR: Command '{e.filename}' not found. Check build-essential.", file=sys.stderr); raise
    except subprocess.CalledProcessError:
        raise # Error already printed, just re-raise
    except Exception as e:
        print(f"ERROR: Unexpected error running command {' '.join(cmd)}: {e}", file=sys.stderr); raise


def ensure_talib_installed():
    """Installs TA-Lib C library and Python wrapper if missing."""
    print(f"--- Starting TA-Lib Installation Check ---")
    
    # Create the custom prefix directory structure with full permissions
    os.makedirs(COMPILED_LIB_DIR, exist_ok=True)
    os.makedirs(COMPILED_INCLUDE_DIR, exist_ok=True)
    # Also create the subdirectory we know will be needed
    os.makedirs(os.path.join(COMPILED_INCLUDE_DIR, "ta-lib"), exist_ok=True)
    
    print(f"Target custom installation prefix: {INSTALL_PREFIX}")
    print(f"Checking for C library: {COMPILED_LIB_PATH_CHECK}")

    lock_acquired = False
    try:
        # --- Lock File Logic ---
        if os.path.exists(_INSTALL_LOCK_FILE):
            mod_time = os.path.getmtime(_INSTALL_LOCK_FILE)
            if (time.time() - mod_time) < 300:
                 print(f"WARN: Lock file '{_INSTALL_LOCK_FILE}' is recent. Skipping."); return
            else:
                print(f"WARN: Stale lock file '{_INSTALL_LOCK_FILE}' found. Removing.")
                try: os.remove(_INSTALL_LOCK_FILE)
                except OSError as e: print(f"WARN: Failed to remove stale lock file: {e}", file=sys.stderr)
        try:
            with open(_INSTALL_LOCK_FILE, 'w') as f: f.write(f"Locked at {time.time()} by PID {os.getpid()}")
            lock_acquired = True; print("Acquired installation lock.")
        except OSError as e:
             print(f"WARN: Could not create lock file: {e}", file=sys.stderr)

        # --- Stage 1: Build and Install C Library ---
        if not os.path.exists(COMPILED_LIB_PATH_CHECK):
            print(f"INFO: TA-Lib C library check failed. Attempting build...")

            # --- Checks ---
            if shutil.which("make") is None or shutil.which("gcc") is None:
                msg = "Build tools ('make', 'gcc') not found. Ensure 'build-essential' is in packages.txt."
                print(f"ERROR: {msg}", file=sys.stderr); raise RuntimeError(msg)
            if not os.path.exists(TARBALL_PATH_SRC):
                msg = f"TA-Lib source tarball not found at '{TARBALL_PATH_SRC}'."
                print(f"ERROR: {msg}", file=sys.stderr); raise FileNotFoundError(msg)

            # --- Cleanup /tmp ---
            if os.path.exists(TARBALL_PATH_TMP):
                try: os.remove(TARBALL_PATH_TMP)
                except OSError as e: print(f"WARN: Could not remove temp tarball: {e}", file=sys.stderr)
            if os.path.exists(EXTRACTED_DIR_TMP):
                try: shutil.rmtree(EXTRACTED_DIR_TMP)
                except OSError as e: print(f"WARN: Could not remove temp extracted dir: {e}", file=sys.stderr)

            default_cwd = os.getcwd()
            print(f"Original working directory: {default_cwd}")

            try:
                # --- Copy and Extract ---
                print(f"Copying {TARBALL_NAME} to /tmp...")
                shutil.copy(TARBALL_PATH_SRC, TARBALL_PATH_TMP)
                
                # Extract tarball (using cwd for tar)
                print(f"Extracting {TARBALL_NAME}...")
                _run_command(["tar", "-xzf", TARBALL_PATH_TMP], cwd="/tmp", error_message=f"Failed to extract {TARBALL_NAME}")

                if not os.path.isdir(EXTRACTED_DIR_TMP): 
                    raise FileNotFoundError(f"Extraction failed: '{EXTRACTED_DIR_TMP}' not found.")

                # --- Configure ---
                print(f"Configuring TA-Lib (running in '{EXTRACTED_DIR_TMP}')...")
                _run_command(["./configure", f"--prefix={INSTALL_PREFIX}"],
                             cwd=EXTRACTED_DIR_TMP, error_message="Configure script failed", check=True)

                # --- Compile ---
                print(f"Compiling TA-Lib (running in '{EXTRACTED_DIR_TMP}')...")
                _run_command(["make"],
                             cwd=EXTRACTED_DIR_TMP, error_message="'make' command failed", check=True)

                # --- Install ---
                print(f"Installing TA-Lib (running in '{EXTRACTED_DIR_TMP}')...")
                _run_command(["make", "install"],
                             cwd=EXTRACTED_DIR_TMP, error_message="'make install' command failed", check=True)

                # --- Post-Install Verification ---
                print(f"Verifying installation artifact: {COMPILED_LIB_PATH_CHECK}")
                if not os.path.exists(COMPILED_LIB_PATH_CHECK):
                     print(f"ERROR: Library file '{COMPILED_LIB_PATH_CHECK}' still not found after install.", file=sys.stderr)
                     _run_command(["ls", "-la", COMPILED_LIB_DIR], check=False)
                     raise FileNotFoundError(f"Installation failed verification.")
                else:
                    print("INFO: TA-Lib C library built and installed successfully!")

            except Exception as e:
                 if os.getcwd() != default_cwd:
                     os.chdir(default_cwd)
                 raise

        else:
            print(f"INFO: Found existing TA-Lib C library: {COMPILED_LIB_PATH_CHECK}")

        # --- Stage 2: Install Python Wrapper ---
        print("INFO: Checking TA-Lib Python wrapper...")
        try:
            import talib
            print(f"INFO: TA-Lib Python wrapper already importable (Version: {getattr(talib, '__version__', 'N/A')}).")
        except ImportError:
            print("INFO: TA-Lib Python wrapper not importable. Attempting installation via pip...")
            try:
                # Use the custom locations for our TA-Lib installation
                include_dir_effective = COMPILED_INCLUDE_DIR
                lib_dir_effective = COMPILED_LIB_DIR

                if not os.path.isdir(include_dir_effective): 
                    raise FileNotFoundError(f"Include directory '{include_dir_effective}' not found!")
                if not os.path.isdir(lib_dir_effective): 
                    raise FileNotFoundError(f"Library directory '{lib_dir_effective}' not found!")

                # Set TA_LIBRARY_PATH and TA_INCLUDE_PATH for pip install
                pip_env = os.environ.copy()
                pip_env["TA_LIBRARY_PATH"] = lib_dir_effective
                pip_env["TA_INCLUDE_PATH"] = include_dir_effective
                pip_env["LD_LIBRARY_PATH"] = lib_dir_effective + os.pathsep + pip_env.get('LD_LIBRARY_PATH', '')

                # Build the pip command
                pip_install_command = [
                    sys.executable, "-m", "pip", "install", "--no-cache-dir",
                    "--global-option=build_ext",
                    f"--global-option=--include-dirs={include_dir_effective}",
                    f"--global-option=--library-dirs={lib_dir_effective}",
                    PYTHON_WRAPPER_VERSION
                ]
                
                # Run the pip command with environment variables set
                subprocess.run(pip_install_command, env=pip_env, check=True)
                print("INFO: TA-Lib Python wrapper installed successfully via pip.")

                # Verify import works
                try:
                    import importlib
                    try:
                        import talib
                        importlib.reload(talib)
                    except ImportError:
                        # If direct import fails, modify sys.path to include library location
                        sys.path.insert(0, lib_dir_effective)
                        import talib
                        importlib.reload(talib)
                    
                    print(f"INFO: TA-Lib successfully imported (Version: {getattr(talib, '__version__', 'N/A')}).")
                except ImportError as post_install_e:
                    print(f"ERROR: Import failed after pip install: {post_install_e}", file=sys.stderr)
                    # Let's try to create a workaround by adding the library to the global LD_LIBRARY_PATH at runtime
                    try:
                        # Create a tiny module that adds the lib path to LD_LIBRARY_PATH on import
                        with open(os.path.join(_SCRIPT_DIR, "talib_loader.py"), "w") as f:
                            f.write(f"""
# Auto-generated by install_talib.py
import os
import sys

# Add custom lib path to LD_LIBRARY_PATH
custom_lib_path = "{COMPILED_LIB_DIR}"
os.environ["LD_LIBRARY_PATH"] = custom_lib_path + os.pathsep + os.environ.get("LD_LIBRARY_PATH", "")

# Try importing talib now
try:
    import talib
    # Forward all attributes from talib to this module
    for name in dir(talib):
        if not name.startswith('__'):
            globals()[name] = getattr(talib, name)
    # Add the version attribute
    __version__ = getattr(talib, '__version__', 'Unknown')
except ImportError as e:
    print(f"Error: Failed to import talib even with LD_LIBRARY_PATH set: {{e}}")
    raise
""")
                        print("Created talib_loader.py workaround. Use 'from utils import talib_loader as talib' in your app.")
                    except Exception as e:
                        print(f"Failed to create workaround: {e}", file=sys.stderr)
                    
                    raise RuntimeError("Failed import verification") from post_install_e

            except Exception as e:
                print(f"FATAL: Pip install failed: {e}", file=sys.stderr); raise

        print("--- TA-Lib Installation Check Completed Successfully ---")

    except Exception as e:
         print(f"\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!", file=sys.stderr)
         print(f"FATAL ERROR during TA-Lib setup: {type(e).__name__}: {e}", file=sys.stderr)
         print(f"Traceback:\n{traceback.format_exc()}", file=sys.stderr)
         print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n", file=sys.stderr)
         raise

    finally:
         if lock_acquired and os.path.exists(_INSTALL_LOCK_FILE):
            print("Releasing installation lock.")
            try: os.remove(_INSTALL_LOCK_FILE)
            except OSError as e: print(f"WARN: Failed to remove lock file: {e}", file=sys.stderr)

# Add a help function that creates a talib importer
def get_talib():
    """Helper function to import talib, handling custom lib paths if needed"""
    # Ensure the library is installed
    ensure_talib_installed()
    
    # Try regular import first
    try:
        import talib
        return talib
    except ImportError:
        # If that fails, try with explicit path
        lib_dir = os.path.join(CUSTOM_PREFIX, "lib")
        os.environ["LD_LIBRARY_PATH"] = lib_dir + os.pathsep + os.environ.get("LD_LIBRARY_PATH", "")
        try:
            import talib
            return talib
        except ImportError as e:
            # Last resort - see if we created the loader module
            loader_path = os.path.join(_SCRIPT_DIR, "talib_loader.py") 
            if os.path.exists(loader_path):
                import importlib.util
                spec = importlib.util.spec_from_file_location("talib_loader", loader_path)
                talib_loader = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(talib_loader)
                return talib_loader
            else:
                raise ImportError(f"Failed to import talib after all attempts: {e}")