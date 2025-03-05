import logging
import os

def setup_logger(name, log_file='app2.log'):
    # Create a logger with the specified name
    logger = logging.getLogger(name)

    # Set the logging level to DEBUG
    logger.setLevel(logging.DEBUG)

    # Determine the directory for the log file and create it if necessary
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Create a file handler for writing logs to a file
    file_handler = logging.FileHandler(log_file)

    # Set level and format for the file handler
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)

    # Add the file handler to the logger
    logger.addHandler(file_handler)

    # Optionally, add a console handler as well
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    
    logger.addHandler(console_handler)

    return logger