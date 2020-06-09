#!/bin/bash
python setup.py sdist bdist_wheel
twine upload dist/sonyapilib-0.4.4-py3-none-any.whl dist/sonyapilib-0.4.4.tar.gz dist/sonyapilib-0.4.5-py3-none-any.whl dist/sonyapilib-0.4.5.tar.gz
