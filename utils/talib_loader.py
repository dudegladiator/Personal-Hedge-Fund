import os
import sys
import importlib

# Get the project root path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Set up paths to the pre-compiled library and include files
lib_path = os.path.join(project_root, 'lib', 'talib', 'lib')
include_path = os.path.join(project_root, 'lib', 'talib', 'include')

# Add the library path to LD_LIBRARY_PATH
os.environ['LD_LIBRARY_PATH'] = lib_path + os.pathsep + os.environ.get('LD_LIBRARY_PATH', '')

# Try to import talib
try:
    import talib
    print(f"Successfully imported TA-Lib version: {getattr(talib, '__version__', 'unknown')}")
except ImportError:
    print("TA-Lib not installed. Installing with pip using pre-compiled library...")
    import subprocess
    
    # Install talib using our pre-compiled library
    pip_env = os.environ.copy()
    pip_env['TA_LIBRARY_PATH'] = lib_path
    pip_env['TA_INCLUDE_PATH'] = include_path
    
    # Run pip install
    subprocess.run([
        sys.executable, '-m', 'pip', 'install', '--no-cache-dir',
        f'--global-option=build_ext',
        f'--global-option=--include-dirs={include_path}',
        f'--global-option=--library-dirs={lib_path}',
        'TA-Lib'
    ], env=pip_env, check=True)
    
    # Now import should work
    import talib
    print(f"Installed and imported TA-Lib version: {getattr(talib, '__version__', 'unknown')}")

# Return the talib module
talib_module = talib