import os
import sys
import subprocess
import shutil
import time

# --- Configuration ---
# Dynamically determine the install prefix based on the current Python environment
INSTALL_PREFIX = sys.prefix
print(f"INFO: Using installation prefix: {INSTALL_PREFIX}")

TARBALL_NAME = "ta-lib-0.6.4-src.tar.gz"
EXTRACTED_DIR_NAME = "ta-lib-0.6.4"

# Assume this script (talib_installer.py) is in the same directory as app.py and the tarball
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) # Use abspath for robustness
TARBALL_PATH_SRC = os.path.join(_SCRIPT_DIR, TARBALL_NAME) # Use os.path.join

TARBALL_PATH_TMP = f"/tmp/{TARBALL_NAME}"
EXTRACTED_DIR_TMP = f"/tmp/{EXTRACTED_DIR_NAME}"

# Define expected locations based on the dynamic prefix
COMPILED_LIB_DIR = os.path.join(INSTALL_PREFIX, "lib")
COMPILED_INCLUDE_DIR = os.path.join(INSTALL_PREFIX, "include", "ta-lib") # Usually includes a ta-lib subdir
COMPILED_LIB_PATH_CHECK = os.path.join(COMPILED_LIB_DIR, "libta_lib.so.0") # Specific file to check
# Alternative check if filename varies: check if libta_lib.so exists (less specific)
# COMPILED_LIB_PATH_CHECK_ALT = os.path.join(COMPILED_LIB_DIR, "libta_lib.so")

# Python wrapper version - USE LATEST COMPATIBLE or pin to known good like 0.4.28
# 0.6.4 is NOT a valid Python wrapper version number from PyPI.
PYTHON_WRAPPER_VERSION = "ta-lib" # Install latest compatible python wrapper
# PYTHON_WRAPPER_VERSION = "ta-lib==0.4.28" # Or pin to a specific known good version

_INSTALL_LOCK_FILE = "/tmp/talib_install.lock" # Optional lock file

def _run_command(cmd, cwd=None, error_message="Command failed"):
    """Helper function to run subprocess commands and print output."""
    print(f"--> Running command: {' '.join(cmd)}" + (f" in {cwd}" if cwd else ""))
    try:
        # Set environment variable for library path *during build* if needed,
        # though make install with correct prefix *should* handle it.
        env = os.environ.copy()
        # env['LD_LIBRARY_PATH'] = COMPILED_LIB_DIR + os.pathsep + env.get('LD_LIBRARY_PATH', '')
        # env['CPATH'] = COMPILED_INCLUDE_DIR + os.pathsep + env.get('CPATH', '')

        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False, env=env)

        if result.stdout:
            print(f"  --- stdout ---:\n{result.stdout.strip()}\n  --------------")
        if result.stderr:
            # Print stderr to stderr for better log separation
            print(f"  --- stderr ---:\n{result.stderr.strip()}\n  --------------", file=sys.stderr)

        if result.returncode != 0:
            print(f"ERROR: {error_message}. Exit code: {result.returncode}", file=sys.stderr)
            # Raise error with captured output
            raise subprocess.CalledProcessError(result.returncode, cmd, output=result.stdout, stderr=result.stderr)

        print(f"<-- Command finished successfully: {' '.join(cmd)}")
        return result

    except FileNotFoundError as e:
        print(f"ERROR: Command '{e.filename}' not found. Ensure required tools (like tar, make, gcc) are installed.", file=sys.stderr)
        print("On Streamlit Cloud, ensure 'build-essential' is in packages.txt.", file=sys.stderr)
        raise # Re-raise the specific error

def ensure_talib_installed():
    """
    Checks for TA-Lib C library and Python wrapper.
    Builds/installs them if they are missing using sys.prefix.
    """
    print(f"--- Starting TA-Lib Installation Check (using {TARBALL_NAME}) ---")
    print(f"Target environment prefix: {INSTALL_PREFIX}")

    lock_acquired = False
    try:
        # --- Optional Lock File Logic ---
        if os.path.exists(_INSTALL_LOCK_FILE):
            mod_time = os.path.getmtime(_INSTALL_LOCK_FILE)
            if (time.time() - mod_time) < 300: # 5 minutes threshold
                 print(f"WARN: Lock file '{_INSTALL_LOCK_FILE}' is recent. Assuming another process is installing. Skipping.")
                 return
            else:
                print(f"WARN: Stale lock file '{_INSTALL_LOCK_FILE}' found. Removing.")
                try: os.remove(_INSTALL_LOCK_FILE)
                except OSError as e: print(f"WARN: Failed to remove stale lock file: {e}", file=sys.stderr)
        try:
            with open(_INSTALL_LOCK_FILE, 'w') as f: f.write(f"Locked at {time.time()} by PID {os.getpid()}")
            lock_acquired = True
            print("Acquired installation lock.")
        except OSError as e:
             print(f"WARN: Could not create lock file '{_INSTALL_LOCK_FILE}': {e}. Proceeding without lock.", file=sys.stderr)
        # --- End Lock File Logic ---


        # --- Stage 1: Build and Install C Library ---
        # Check if the library *file* specifically exists
        c_lib_exists = os.path.exists(COMPILED_LIB_PATH_CHECK)
        # Add alternative check if needed: c_lib_exists = c_lib_exists or os.path.exists(COMPILED_LIB_PATH_CHECK_ALT)

        if not c_lib_exists:
            print(f"INFO: TA-Lib C library check failed ({COMPILED_LIB_PATH_CHECK} not found).")
            print("Attempting C library build and install...")

            # Dependency Checks
            if shutil.which("make") is None or shutil.which("gcc") is None:
                msg = "Build tools ('make', 'gcc') not found. Ensure 'build-essential' is in packages.txt."
                print(f"ERROR: {msg}", file=sys.stderr)
                raise RuntimeError(msg)
            if not os.path.exists(TARBALL_PATH_SRC):
                msg = f"TA-Lib source tarball not found at '{TARBALL_PATH_SRC}'."
                print(f"ERROR: {msg}", file=sys.stderr)
                raise FileNotFoundError(msg)

            # Cleanup /tmp
            print("Cleaning up potentially leftover temporary files...")
            if os.path.exists(TARBALL_PATH_TMP):
                try: os.remove(TARBALL_PATH_TMP)
                except OSError as e: print(f"WARN: Could not remove temp tarball: {e}", file=sys.stderr)
            if os.path.exists(EXTRACTED_DIR_TMP):
                try: shutil.rmtree(EXTRACTED_DIR_TMP)
                except OSError as e: print(f"WARN: Could not remove temp extracted dir: {e}", file=sys.stderr)

            os.makedirs("/tmp", exist_ok=True)
            default_cwd = os.getcwd() # Store original directory

            try:
                # --- Build Process ---
                print(f"Copying {TARBALL_NAME} to /tmp...")
                shutil.copy(TARBALL_PATH_SRC, TARBALL_PATH_TMP)

                os.chdir("/tmp")
                print(f"Extracting {TARBALL_NAME} in /tmp...")
                _run_command(["tar", "-zxvf", TARBALL_PATH_TMP], error_message=f"Failed to extract {TARBALL_NAME}")

                if not os.path.isdir(EXTRACTED_DIR_TMP):
                    # List /tmp contents for debugging extraction issues
                    try:
                        ls_output = subprocess.check_output(["ls", "-la", "/tmp"], text=True)
                        print(f"--- Contents of /tmp after extraction attempt ---\n{ls_output}\n-------------------------")
                    except Exception as e:
                        print(f"WARN: Could not list contents of /tmp: {e}", file=sys.stderr)
                    raise FileNotFoundError(f"Extraction failed: '{EXTRACTED_DIR_TMP}' not found")

                os.chdir(EXTRACTED_DIR_TMP)
                print(f"Configuring TA-Lib C library for prefix '{INSTALL_PREFIX}'...")
                _run_command(["./configure", f"--prefix={INSTALL_PREFIX}"], error_message="Configure script failed")

                print("Compiling TA-Lib C library (make)...")
                _run_command(["make"], error_message="'make' command failed")

                print("Installing TA-Lib C library (make install)...")
                # No need to create INSTALL_PREFIX manually, make install should handle it with correct permissions.
                _run_command(["make", "install"], error_message="'make install' command failed")

                # Re-check after installation
                if not os.path.exists(COMPILED_LIB_PATH_CHECK):
                     print(f"ERROR: 'make install' seemed successful, but target library '{COMPILED_LIB_PATH_CHECK}' still not found.", file=sys.stderr)
                     # List contents of install directory for debugging
                     if os.path.isdir(COMPILED_LIB_DIR):
                         try:
                             ls_output = subprocess.check_output(["ls", "-la", COMPILED_LIB_DIR], text=True)
                             print(f"--- Contents of {COMPILED_LIB_DIR} ---\n{ls_output}\n-------------------------")
                         except Exception as e:
                             print(f"WARN: Could not list contents of {COMPILED_LIB_DIR}: {e}", file=sys.stderr)
                     else:
                         print(f"WARN: Install directory {COMPILED_LIB_DIR} does not exist.", file=sys.stderr)
                     raise FileNotFoundError(f"Installation failed verification: {COMPILED_LIB_PATH_CHECK} missing")
                else:
                    print("INFO: TA-Lib C library built and installed successfully!")

            finally:
                # --- Cleanup & Return ---
                print(f"Returning to original directory: {default_cwd}")
                os.chdir(default_cwd)
                # Optional: Clean up /tmp files now? Better to leave for debugging unless space is critical.
                # print("INFO: Cleaning up temporary build files...")
                # if os.path.exists(TARBALL_PATH_TMP): os.remove(TARBALL_PATH_TMP)
                # if os.path.exists(EXTRACTED_DIR_TMP): shutil.rmtree(EXTRACTED_DIR_TMP)
        else:
            print(f"INFO: Found existing TA-Lib C library at {COMPILED_LIB_PATH_CHECK}.")

        # --- Stage 2: Install Python Wrapper ---
        print("INFO: Checking TA-Lib Python wrapper...")
        try:
            # Try importing to see if it's already installed and working
            import talib
            # Optionally check version if needed: print(f"Found TA-Lib version: {talib.__version__}")
            print("INFO: TA-Lib Python wrapper already importable.")
        except ImportError:
            print("INFO: TA-Lib Python wrapper not importable. Attempting installation...")
            try:
                # Verify the include/lib directories exist before telling pip to use them
                include_dir_effective = os.path.join(INSTALL_PREFIX, 'include')
                lib_dir_effective = os.path.join(INSTALL_PREFIX, 'lib')

                if not os.path.isdir(include_dir_effective):
                    print(f"ERROR: Include directory '{include_dir_effective}' needed for pip install does not exist!", file=sys.stderr)
                    raise FileNotFoundError(f"Missing include directory: {include_dir_effective}")
                if not os.path.isdir(lib_dir_effective):
                     print(f"ERROR: Library directory '{lib_dir_effective}' needed for pip install does not exist!", file=sys.stderr)
                     raise FileNotFoundError(f"Missing library directory: {lib_dir_effective}")

                # Construct pip command with dynamic paths
                pip_install_command = [
                    sys.executable, "-m", "pip", "install",
                    "--no-cache-dir", # Crucial to prevent stale builds
                    # Use the verified include/lib directories
                    f"--config-settings=build_ext=--include-dirs={include_dir_effective}",
                    f"--config-settings=build_ext=--library-dirs={lib_dir_effective}",
                    PYTHON_WRAPPER_VERSION # Install specific or latest wrapper
                ]
                _run_command(pip_install_command, error_message="Failed to install TA-Lib Python wrapper using pip")
                print("INFO: TA-Lib Python wrapper installed successfully via pip.")

                # Final verification: Try importing again *after* install
                try:
                    import talib
                    print("INFO: TA-Lib successfully imported after installation!")
                except ImportError as post_install_e:
                    print(f"ERROR: Still failed to import talib after pip install: {post_install_e}", file=sys.stderr)
                    print("Check pip install logs above. LD_LIBRARY_PATH might need adjustment in the runtime environment?", file=sys.stderr)
                    # Note: Streamlit Cloud usually handles LD_LIBRARY_PATH correctly if installed to sys.prefix/lib
                    raise RuntimeError("Failed import verification after installation") from post_install_e

            except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError, Exception) as e:
                print(f"FATAL: An error occurred during TA-Lib Python wrapper installation: {e}", file=sys.stderr)
                raise # Re-raise the fatal error

        print("--- TA-Lib Installation Check Completed ---")

    except Exception as e:
         # Catch any exception from the process and print clearly
         import traceback
         print(f"\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!", file=sys.stderr)
         print(f"FATAL ERROR during TA-Lib setup: {type(e).__name__}: {e}", file=sys.stderr)
         print(f"Traceback:\n{traceback.format_exc()}", file=sys.stderr)
         print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n", file=sys.stderr)
         raise # Re-raise the exception so the calling code knows it failed

    finally:
        # --- Remove Lock File ---
        if lock_acquired and os.path.exists(_INSTALL_LOCK_FILE):
            print("Releasing installation lock.")
            try: os.remove(_INSTALL_LOCK_FILE)
            except OSError as e: print(f"WARN: Failed to remove lock file '{_INSTALL_LOCK_FILE}': {e}", file=sys.stderr)