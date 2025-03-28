import sys
import os
sys.path.insert(0, os.path.abspath('../src'))

import re
from liveimport import __version__

project = 'LiveImport'
copyright = '2025, Edward Screven'
author = 'Edward Screven'

version = re.match(r"\d+\.\d+",__version__)[0]  #type:ignore
release = __version__

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.intersphinx',
    'sphinx_rtd_theme',
]

# No templates or static elements for now.
# templates_path = ['_templates']
# html_static_path = ['_static']

exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

language = 'en'

html_theme = 'sphinx_rtd_theme'
html_show_sourcelink = False

intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
}
