import os
import sys

# Make Core/ importable as a flat module namespace (no packaging yet, #12).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Core'))
