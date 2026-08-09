import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'Core'))
from engine_scraper import update_all_data
import config

if __name__ == '__main__':
    update_all_data(config.DATA_DIR, year=2020, force_rebuild=False)
