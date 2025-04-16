import os
import sys
import subprocess
import shutil
import time
import traceback # For detailed error printing

# --- Configuration ---
# Dynamically determine the install prefix based on the current Python environment
INSTALL_PREFIX = sys.prefix
print(f"INFO: Using installation prefix: {INSTALL_PREFIX}")

TARBALL_NAME = "ta-lib-0.6.4-src.tar.gz"
# Confirmed from previous error - directory inside tarball is ta-lib-0.6.4
EXTRACTED_DIR_NAME = "ta-lib-0.6.4"

# Assume this script (install_talib.py) is in the same directory as app.py and the tarball
# OR adjust path relative to this script's location if needed.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# If tarball is in the *parent* directory of this script (e.g., script is in utils/, tarball in root)
# TARBALL_PATH_SRC = os.path.abspath(os.path.join(_SCRIPT_DIR, '..', TARBALL_NAME))
# If tarball is in the *same* directory as this script
TARBALL_PATH_SRC = os.path.join(_SCRIPT_DIR, TARBALL_NAME) # Check if this is correct for your structure

TARBALL_PATH_TMP = f"/tmp/{TARBALL_NAME}"
EXTRACTED_DIR_TMP = f"/tmp/{EXTRACTED_DIR_NAME}" # Path within /tmp after extraction

# Define expected locations based on the dynamic prefix
COMPILED_LIB_DIR = os.path.join(INSTALL_PREFIX, "lib")
COMPILED_INCLUDE_DIR = os.path.join(INSTALL_PREFIX, "include") # Include dir itself
COMPILED_TA_INCLUDE_DIR = os.path.join(COMPILED_INCLUDE_DIR, "ta-lib") # Specific ta-lib subdir often created
COMPILED_LIB_PATH_CHECK = os.path.join(COMPILED_LIB_DIR, "libta_lib.so.0") # Main library file to check

# Python wrapper version - Use latest compatible or pin to known good like 0.4.28
PYTHON_WRAPPER_VERSION = "TA-Lib" # Use canonical name from PyPI (case-insensitive usually fine)
# PYTHON_WRAPPER_VERSION = "TA-Lib==0.4.28" # Or pin to a specific known good version

_INSTALL_LOCK_FILE = "/tmp/talib_install.lock"

def _run_command(cmd, cwd=None, error_message="Command failed", check=True):
    """
    Helper function to run subprocess commands, print output, and handle errors.
    'check=True' will raise CalledProcessError on non-zero exit code.
    """
    print(f"--> Running command: {' '.join(cmd)}" + (f" in '{cwd}'" if cwd else ""))
    try:
        env = os.environ.copy()
        # Ensure library path includes the install dir *if* needed for subsequent commands
        # env['LD_LIBRARY_PATH'] = COMPILED_LIB_DIR + os.pathsep + env.get('LD_LIBRARY_PATH', '')

        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False, env=env) # Run with check=False initially to log output

        if result.stdout:
            print(f"  --- stdout ---:\n{result.stdout.strip()}\n  --------------")
        if result.stderr:
            print(f"  --- stderr ---:\n{result.stderr.strip()}\n  --------------", file=sys.stderr)

        if check and result.returncode != 0: # Check return code manually if check=True was passed
            print(f"ERROR: {error_message}. Exit code: {result.returncode}", file=sys.stderr)
            raise subprocess.CalledProcessError(result.returncode, cmd, output=result.stdout, stderr=result.stderr)
        elif not check and result.returncode != 0:
             print(f"WARN: Command finished with non-zero exit code ({result.returncode}) but check=False. Message: {error_message}", file=sys.stderr)


        print(f"<-- Command finished: {' '.join(cmd)} (Exit Code: {result.returncode})")
        return result

    except FileNotFoundError as e:
        print(f"ERROR: Command '{e.filename}' not found. Ensure required tools (tar, make, gcc) are installed.", file=sys.stderr)
        print("On Streamlit Cloud, ensure 'build-essential' is in packages.txt.", file=sys.stderr)
        raise
    except subprocess.CalledProcessError:
        # Error message already printed above
        raise # Re-raise the error after logging
    except Exception as e:
        print(f"ERROR: Unexpected error running command {' '.join(cmd)}: {e}", file=sys.stderr)
        raise


def ensure_talib_installed():
    """
    Checks for TA-Lib C library and Python wrapper.
    Builds/installs them if they are missing using sys.prefix.
    Uses cwd for build commands to avoid changing the main script's directory.
    """
    print(f"--- Starting TA-Lib Installation Check (using {TARBALL_NAME}) ---")
    print(f"Target environment prefix: {INSTALL_PREFIX}")
    print(f"Checking for C library: {COMPILED_LIB_PATH_CHECK}")

    lock_acquired = False
    try:
        # --- Optional Lock File Logic ---
        if os.path.exists(_INSTALL_LOCK_FILE):
            mod_time = os.path.getmtime(_INSTALL_LOCK_FILE)
            if (time.time() - mod_time) < 300:
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
        c_lib_exists = os.path.exists(COMPILED_LIB_PATH_CHECK)

        if not c_lib_exists:
            print(f"INFO: TA-Lib C library check failed.")
            print("Attempting C library build and install...")

            # --- Dependency and Source Checks ---
            if shutil.which("make") is None or shutil.which("gcc") is None:
                msg = "Build tools ('make', 'gcc') not found. Ensure 'build-essential' is in packages.txt."
                print(f"ERROR: {msg}", file=sys.stderr); raise RuntimeError(msg)
            if not os.path.exists(TARBALL_PATH_SRC):
                msg = f"TA-Lib source tarball not found at '{TARBALL_PATH_SRC}'. Check path relative to install_talib.py."
                print(f"ERROR: {msg}", file=sys.stderr); raise FileNotFoundError(msg)

            # --- Cleanup /tmp ---
            print("Cleaning up potentially leftover temporary files in /tmp...")
            if os.path.exists(TARBALL_PATH_TMP):
                try: os.remove(TARBALL_PATH_TMP)
                except OSError as e: print(f"WARN: Could not remove temp tarball: {e}", file=sys.stderr)
            if os.path.exists(EXTRACTED_DIR_TMP):
                try: shutil.rmtree(EXTRACTED_DIR_TMP)
                except OSError as e: print(f"WARN: Could not remove temp extracted dir: {e}", file=sys.stderr)

            os.makedirs("/tmp", exist_ok=True)
            default_cwd = os.getcwd() # Store original directory (should be project root)
            print(f"Original working directory: {default_cwd}")

            try:
                # --- Copy and Extract in /tmp ---
                print(f"Copying {TARBALL_NAME} to /tmp...")
                shutil.copy(TARBALL_PATH_SRC, TARBALL_PATH_TMP)
                if not os.path.exists(TARBALL_PATH_TMP):
                     raise FileNotFoundError(f"Failed to copy tarball to {TARBALL_PATH_TMP}")
                print(f"Tarball successfully copied to {TARBALL_PATH_TMP}")

                # Change to /tmp ONLY for extraction step
                print(f"Changing directory temporarily to /tmp for extraction.")
                os.chdir("/tmp")

                print(f"Extracting {TARBALL_NAME}...")
                # Run tar command in the current directory (/tmp)
                _run_command(["tar", "-zxvf", TARBALL_PATH_TMP], error_message=f"Failed to extract {TARBALL_NAME}")

                # --- IMPORTANT: Change back immediately ---
                print(f"Changing directory back to {default_cwd}")
                os.chdir(default_cwd) # <<<<<<< CHANGE BACK HERE

                # --- Verify Extraction Result ---
                print(f"Verifying extraction directory: {EXTRACTED_DIR_TMP}")
                if not os.path.isdir(EXTRACTED_DIR_TMP):
                    try:
                        ls_output = subprocess.check_output(["ls", "-la", "/tmp"], text=True)
                        print(f"--- Contents of /tmp after extraction attempt ---\n{ls_output}\n-------------------------")
                    except Exception as e: print(f"WARN: Could not list contents of /tmp: {e}", file=sys.stderr)
                    raise FileNotFoundError(f"Extraction failed: '{EXTRACTED_DIR_TMP}' not found after tar command.")

                # --- Run Build Steps using cwd= ---
                # --- DO NOT os.chdir() into EXTRACTED_DIR_TMP ---
                print(f"Configuring TA-Lib C library (running in '{EXTRACTED_DIR_TMP}')...")
                _run_command(["./configure", f"--prefix={INSTALL_PREFIX}"],
                             cwd=EXTRACTED_DIR_TMP, # <<< Use cwd argument
                             error_message="Configure script failed", check=True)

                print(f"Compiling TA-Lib C library (running in '{EXTRACTED_DIR_TMP}')...")
                _run_command(["make"],
                             cwd=EXTRACTED_DIR_TMP, # <<< Use cwd argument
                             error_message="'make' command failed", check=True)

                print(f"Installing TA-Lib C library (running in '{EXTRACTED_DIR_TMP}')...")
                # Ensure target prefix dirs exist before install
                os.makedirs(COMPILED_LIB_DIR, exist_ok=True)
                os.makedirs(COMPILED_INCLUDE_DIR, exist_ok=True)
                _run_command(["make", "install"],
                             cwd=EXTRACTED_DIR_TMP, # <<< Use cwd argument
                             error_message="'make install' command failed", check=True)

                # --- Post-Install Verification ---
                print(f"Verifying installation artifact: {COMPILED_LIB_PATH_CHECK}")
                if not os.path.exists(COMPILED_LIB_PATH_CHECK):
                     print(f"ERROR: 'make install' completed, but target library '{COMPILED_LIB_PATH_CHECK}' still not found.", file=sys.stderr)
                     if os.path.isdir(COMPILED_LIB_DIR):
                         try:
                             ls_output = subprocess.check_output(["ls", "-la", COMPILED_LIB_DIR], text=True)
                             print(f"--- Contents of {COMPILED_LIB_DIR} ---\n{ls_output}\n-------------------------")
                         except Exception as e: print(f"WARN: Could not list contents of {COMPILED_LIB_DIR}: {e}", file=sys.stderr)
                     else: print(f"WARN: Install directory {COMPILED_LIB_DIR} does not exist.", file=sys.stderr)
                     raise FileNotFoundError(f"Installation failed verification: {COMPILED_LIB_PATH_CHECK} missing")
                else:
                    print("INFO: TA-Lib C library built and installed successfully!")

            except Exception as e: # Catch any error during build process
                 # Ensure we change back if an error happened after chdir('/tmp') but before planned chdir back
                 if os.getcwd() != default_cwd:
                     print(f"ERROR occurred during build, ensuring directory is reset to {default_cwd}")
                     os.chdir(default_cwd)
                 raise # Re-raise the exception that occurred during build

            # No finally block needed for chdir, as it's handled explicitly above

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
                # Verify the include/lib directories exist before telling pip
                include_dir_effective = COMPILED_INCLUDE_DIR
                lib_dir_effective = COMPILED_LIB_DIR

                if not os.path.isdir(include_dir_effective):
                    raise FileNotFoundError(f"Include directory '{include_dir_effective}' needed for pip install does not exist!")
                if not os.path.isdir(lib_dir_effective):
                     raise FileNotFoundError(f"Library directory '{lib_dir_effective}' needed for pip install does not exist!")

                # Construct pip command
                pip_install_command = [
                    sys.executable, "-m", "pip", "install",
                    "--no-cache-dir", # Avoid stale builds
                    # Pass hints for C lib location
                    f"--config-settings=build_ext=--include-dirs={include_dir_effective}",
                    f"--config-settings=build_ext=--library-dirs={lib_dir_effective}",
                    PYTHON_WRAPPER_VERSION
                ]
                _run_command(pip_install_command, error_message="Failed to install TA-Lib Python wrapper using pip", check=True)
                print("INFO: TA-Lib Python wrapper installed successfully via pip.")

                # Final verification: Try importing again *after* install
                try:
                    # Ensure Python re-evaluates import paths if necessary
                    import importlib
                    import talib
                    importlib.reload(talib) # Force reload in case path caching was issue
                    print(f"INFO: TA-Lib successfully imported after installation! (Version: {getattr(talib, '__version__', 'N/A')})")
                except ImportError as post_install_e:
                    print(f"ERROR: Still failed to import talib after pip install: {post_install_e}", file=sys.stderr)
                    print("Check pip install logs above. LD_LIBRARY_PATH might need adjustment or the install failed.", file=sys.stderr)
                    raise RuntimeError("Failed import verification after installation") from post_install_e

            except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError, Exception) as e:
                print(f"FATAL: An error occurred during TA-Lib Python wrapper installation: {e}", file=sys.stderr)
                raise

        print("--- TA-Lib Installation Check Completed Successfully ---")

    except Exception as e:
         print(f"\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!", file=sys.stderr)
         print(f"FATAL ERROR during TA-Lib setup: {type(e).__name__}: {e}", file=sys.stderr)
         print(f"Traceback:\n{traceback.format_exc()}", file=sys.stderr)
         print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n", file=sys.stderr)
         raise # Re-raise the exception so the calling app.py knows it failed

    finally:
        # --- Remove Lock File ---
        if lock_acquired and os.path.exists(_INSTALL_LOCK_FILE):
            print("Releasing installation lock.")
            try: os.remove(_INSTALL_LOCK_FILE)
            except OSError as e: print(f"WARN: Failed to remove lock file '{_INSTALL_LOCK_FILE}': {e}", file=sys.stderr)
