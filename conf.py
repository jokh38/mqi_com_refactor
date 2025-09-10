# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import os
import sys

# autodoc이 'src' 모듈을 찾을 수 있도록 프로젝트 루트 디렉터리(현재 디렉터리)를 Python 경로에 추가합니다.
sys.path.insert(0, os.path.abspath('.'))

project = 'mqi'
copyright = '2025, KH Jo'
author = 'KH Jo'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',      # docstring에서 문서를 자동으로 가져옵니다.
    'sphinx.ext.autosummary',  # 모듈/클래스/함수를 표 형태로 깔끔하게 요약합니다.
    'sphinx.ext.napoleon',     # Google 및 NumPy 스타일 docstring을 지원합니다.
    'sphinx.ext.viewcode',     # 문서에서 소스 코드로 바로 이동하는 링크를 추가합니다.
    'sphinx_rtd_theme',        # Read the Docs 테마를 사용합니다.
]

# autosummary가 stub 파일을 자동으로 생성하도록 설정합니다.
autosummary_generate = True

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']
