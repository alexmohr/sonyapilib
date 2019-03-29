# pylint: disable=invalid-name, exec-used
"""Setup sonyapilib package."""
from __future__ import absolute_import
import sys
import os
from setuptools import setup, find_packages
# import subprocess
sys.path.insert(0, '.')

CURRENT_DIR = os.path.dirname(__file__)

# to deploy to pip, please use
# make pythonpack
# python setup.py register sdist upload
# and be sure to test it firstly using "python setup.py register sdist upload -r pypitest"
setup(name='sonyapilib',
  packages = ['sonyapilib'], # this must be the same as the name above
  version = '0.3.10',
  description = 'Lib to control sony devices with theier soap api',
  author = 'Alexander Mohr',
  author_email = 'sonyapilib@mohr.io',
  url = 'https://github.com/alexmohr/sonyapilib', # use the URL to the github repo
  download_url = 'https://codeload.github.com/alexmohr/sonyapilib/tar.gz/0.3.7',
  keywords = ['soap', 'sony', 'api'], # arbitrary keywords
  classifiers = [],
  install_requires=[
      'jsonpickle',
      'setuptools',
      'requests'
  ],

)