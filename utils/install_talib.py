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
EXTRACTED_DIR_NAME = "ta-lib-0.6.4"

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Adjust TARBALL_PATH_SRC based on your project structure:
# If tarball is in the *parent* directory (project root) and this script is in utils/
TARBALL_PATH_SRC = os.path.abspath(os.path.join(_SCRIPT_DIR, '..', TARBALL_NAME))
# If tarball is in the *same* directory as this script
# TARBALL_PATH_SRC = os.path.join(_SCRIPT_DIR, TARBALL_NAME)

print(f"INFO: Looking for source tarball at: {TARBALL_PATH_SRC}")


TARBALL_PATH_TMP = f"/tmp/{TARBALL_NAME}"
EXTRACTED_DIR_TMP = f"/tmp/{EXTRACTED_DIR_NAME}" # Path within /tmp after extraction

COMPILED_LIB_DIR = os.path.join(INSTALL_PREFIX, "lib")
COMPILED_INCLUDE_DIR = os.path.join(INSTALL_PREFIX, "include")
COMPILED_LIB_PATH_CHECK = os.path.join(COMPILED_LIB_DIR, "libta_lib.so.0")

PYTHON_WRAPPER_VERSION = "TA-Lib"

_INSTALL_LOCK_FILE = "/tmp/talib_install.lock"

def _run_command(cmd, cwd=None, error_message="Command failed", check=True):
    """
    Helper function to run subprocess commands, print output, and handle errors.
    'check=True' will raise CalledProcessError on non-zero exit code.
    """
    print(f"--> Running command: {' '.join(cmd)}" + (f" in '{cwd}'" if cwd else ""))
    try:
        env = os.environ.copy()
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False, env=env)

        # Always print stdout, even if short
        print(f"  --- stdout ({len(result.stdout)} bytes) ---:\n{result.stdout.strip()}\n  --------------")
        # Always print stderr, even if short
        print(f"  --- stderr ({len(result.stderr)} bytes) ---:\n{result.stderr.strip()}\n  --------------", file=sys.stderr)

        if check and result.returncode != 0:
            print(f"ERROR: {error_message}. Exit code: {result.returncode}", file=sys.stderr)
            # Re-raise the error *after* printing output
            raise subprocess.CalledProcessError(result.returncode, cmd, output=result.stdout, stderr=result.stderr)
        elif not check and result.returncode != 0:
             print(f"WARN: Command finished with non-zero exit code ({result.returncode}) but check=False. Message: {error_message}", file=sys.stderr)

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
    print(f"Target environment prefix: {INSTALL_PREFIX}")
    print(f"Checking for C library: {COMPILED_LIB_PATH_CHECK}")

    lock_acquired = False
    try:
        # --- Optional Lock File Logic ---
        # (Keep lock file logic as before)
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
             print(f"WARN: Could not create lock file '{_INSTALL_LOCK_FILE}': {e}. Proceeding without lock.", file=sys.stderr)
        # --- End Lock File Logic ---

        # --- Stage 1: Build and Install C Library ---
        if not os.path.exists(COMPILED_LIB_PATH_CHECK):
            print(f"INFO: TA-Lib C library check failed. Attempting build...")

            # --- Prerequisite Checks ---
            if shutil.which("make") is None or shutil.which("gcc") is None:
                msg = "Build tools ('make', 'gcc') not found. Ensure 'build-essential' is in packages.txt."
                print(f"ERROR: {msg}", file=sys.stderr); raise RuntimeError(msg)
            if not os.path.exists(TARBALL_PATH_SRC):
                msg = f"TA-Lib source tarball not found at '{TARBALL_PATH_SRC}'."
                print(f"ERROR: {msg}", file=sys.stderr); raise FileNotFoundError(msg)

            # --- Cleanup /tmp ---
            print("Cleaning up /tmp...")
            # (Keep cleanup logic as before)
            if os.path.exists(TARBALL_PATH_TMP):
                try: os.remove(TARBALL_PATH_TMP)
                except OSError as e: print(f"WARN: Could not remove temp tarball: {e}", file=sys.stderr)
            if os.path.exists(EXTRACTED_DIR_TMP):
                try: shutil.rmtree(EXTRACTED_DIR_TMP)
                except OSError as e: print(f"WARN: Could not remove temp extracted dir: {e}", file=sys.stderr)

            os.makedirs("/tmp", exist_ok=True)
            default_cwd = os.getcwd()
            print(f"Original working directory: {default_cwd}")

            try:
                # --- Copy and Extract ---
                print(f"Copying {TARBALL_NAME} to /tmp...")
                shutil.copy(TARBALL_PATH_SRC, TARBALL_PATH_TMP)
                if not os.path.exists(TARBALL_PATH_TMP): raise FileNotFoundError(f"Copy failed: {TARBALL_PATH_TMP}")

                print(f"Changing directory temporarily to /tmp for extraction.")
                os.chdir("/tmp")
                print(f"Extracting {TARBALL_NAME}...")
                _run_command(["tar", "-zxvf", TARBALL_PATH_TMP], error_message=f"Failed to extract {TARBALL_NAME}")
                print(f"Changing directory back to {default_cwd}")
                os.chdir(default_cwd)

                if not os.path.isdir(EXTRACTED_DIR_TMP): raise FileNotFoundError(f"Extraction failed: '{EXTRACTED_DIR_TMP}' not found.")

                # --- Configure ---
                print(f"Configuring TA-Lib (running in '{EXTRACTED_DIR_TMP}')...")
                _run_command(["./configure", f"--prefix={INSTALL_PREFIX}"],
                             cwd=EXTRACTED_DIR_TMP, error_message="Configure script failed", check=True)

                # --- Compile ---
                print(f"Compiling TA-Lib (running in '{EXTRACTED_DIR_TMP}')...")
                _run_command(["make"],
                             cwd=EXTRACTED_DIR_TMP, error_message="'make' command failed", check=True)

                # --- Pre-Install Checks (DEBUGGING) ---
                print("--- Running Pre-Install Checks ---")
                target_lib_dir = COMPILED_LIB_DIR
                target_include_dir = COMPILED_INCLUDE_DIR
                source_libs_dir = os.path.join(EXTRACTED_DIR_TMP, "src", ".libs")

                print(f"Checking permissions for target lib dir: {target_lib_dir}")
                _run_command(["ls", "-ld", target_lib_dir], error_message="Failed to list target lib dir", check=False) # Check=False, might not exist fully yet
                print(f"Checking permissions for target include dir: {target_include_dir}")
                _run_command(["ls", "-ld", target_include_dir], error_message="Failed to list target include dir", check=False)
                print(f"Listing compiled source libs in: {source_libs_dir}")
                if os.path.isdir(source_libs_dir):
                     _run_command(["ls", "-la", source_libs_dir], error_message="Failed to list source libs", check=False)
                else:
                     print(f"WARN: Source libs directory '{source_libs_dir}' not found before install.")
                print("--- End Pre-Install Checks ---")

                # --- Install ---
                print(f"Installing TA-Lib (running in '{EXTRACTED_DIR_TMP}')...")
                os.makedirs(target_lib_dir, exist_ok=True) # Ensure parent dirs exist
                os.makedirs(target_include_dir, exist_ok=True)
                _run_command(["make", "install"],
                             cwd=EXTRACTED_DIR_TMP, error_message="'make install' command failed", check=True) # check=True crucial here

                # --- Post-Install Verification ---
                print(f"Verifying installation artifact: {COMPILED_LIB_PATH_CHECK}")
                if not os.path.exists(COMPILED_LIB_PATH_CHECK):
                     print(f"ERROR: 'make install' completed, but target library '{COMPILED_LIB_PATH_CHECK}' still not found.", file=sys.stderr)
                     # (Keep the ls -la check here as before)
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
                 if os.getcwd() != default_cwd:
                     print(f"ERROR occurred during build, ensuring directory is reset to {default_cwd}")
                     os.chdir(default_cwd)
                 raise # Re-raise the exception

        else:
            print(f"INFO: Found existing TA-Lib C library: {COMPILED_LIB_PATH_CHECK}")

        # --- Stage 2: Install Python Wrapper ---
        # (Keep Stage 2 logic exactly as before)
        print("INFO: Checking TA-Lib Python wrapper...")
        try:
            import talib
            print(f"INFO: TA-Lib Python wrapper already importable (Version: {getattr(talib, '__version__', 'N/A')}).")
        except ImportError:
            print("INFO: TA-Lib Python wrapper not importable. Attempting installation via pip...")
            try:
                include_dir_effective = COMPILED_INCLUDE_DIR
                lib_dir_effective = COMPICOMPILED_LIB_DIR

                if not os.path.isdir(include_dir_effective): raise FileNotFoundError(f"Include directory '{include_dir_effective}' not found!")
                if not os.path.isdir(lib_dir_effective): raise FileNotFoundError(f"Library directory '{lib_dir_effective}' not found!")

                pip_install_command = [
                    sys.executable, "-m", "pip", "install", "--no-cache-dir",
                    f"--config-settings=build_ext=--include-dirs={include_dir_effective}",
                    f"--config-settings=build_ext=--library-dirs={lib_dir_effective}",
                    PYTHON_WRAPPER_VERSION
                ]
                _run_command(pip_install_command, error_message="Failed pip install", check=True)
                print("INFO: TA-Lib Python wrapper installed successfully via pip.")

                try:
                    import importlib; import talib; importlib.reload(talib)
                    print(f"INFO: TA-Lib successfully imported after installation! (Version: {getattr(talib, '__version__', 'N/A')})")
                except ImportError as post_install_e:
                    print(f"ERROR: Still failed import after pip install: {post_install_e}", file=sys.stderr); raise RuntimeError("Import verify failed") from post_install_e

            except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError, Exception) as e:
                print(f"FATAL: Pip install failed: {e}", file=sys.stderr); raise

        print("--- TA-Lib Installation Check Completed Successfully ---")

    except Exception as e:
         # (Keep general error catching as before)
         print(f"\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!", file=sys.stderr)
         print(f"FATAL ERROR during TA-Lib setup: {type(e).__name__}: {e}", file=sys.stderr)
         print(f"Traceback:\n{traceback.format_exc()}", file=sys.stderr)
         print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n", file=sys.stderr)
         raise

    finally:
        # --- Remove Lock File ---
        # (Keep lock file removal logic as before)
         if lock_acquired and os.path.exists(_INSTALL_LOCK_FILE):
            print("Releasing installation lock.")
            try: os.remove(_INSTALL_LOCK_FILE)
            except OSError as e: print(f"WARN: Failed to remove lock file '{_INSTALL_LOCK_FILE}': {e}", file=sys.stderr)