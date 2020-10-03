# pylint: disable=invalid-name, exec-used
"""Setup sonyapilib package."""
from __future__ import absolute_import

import os
import sys

from setuptools import setup

sys.path.insert(0, '.')

CURRENT_DIR = os.path.dirname(__file__)

# to deploy to pip, please use
# make pythonpack
# python setup.py register sdist upload
# and be sure to test it firstly using
# "python setup.py register sdist upload -r pypitest"
setup(
    name='sonyapilib',
    packages=['sonyapilib'],  # this must be the same as the name above
    version='0.5.0',
    description='Lib to control sony devices with their soap api',
    author='Alexander Mohr',
    author_email='sonyapilib@mohr.io',
    # use the URL to the github repo
    url='https://github.com/alexmohr/sonyapilib',
    download_url='https://codeload.github.com/alexmohr/sonyapilib/tar.gz/0.5.0',
    keywords=['soap', 'sony', 'api'],  # arbitrary keywords
    classifiers=[],
    setup_requires=[
        'wheel'
    ],
    install_requires=[
        'jsonpickle',
        'setuptools',
        'requests',
        'wakeonlan'
    ],
    tests_require=[
        'pytest>=5.4',
        'pytest-pep8',
        'pytest-cov',
        'python-coveralls',
        'pylint',
        'coverage==4.5.4'
    ]
)
