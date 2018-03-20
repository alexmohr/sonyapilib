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
setup(name='braviarc',
      version='0.1.0',
      description=open(os.path.join(CURRENT_DIR, 'README.md')).read(),
      install_requires=['requests'],
      maintainer='Alexander Mohr',
      maintainer_email='sonyapilib@mohr.io',
      zip_safe=False,
      packages=find_packages(),
      include_package_data=True,
      url='https://github.com/alexmohr/sonyapilib.git')
1