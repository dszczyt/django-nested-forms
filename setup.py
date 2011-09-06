#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    name='django-nested-forms',
    version="0.1",
    author='Damien Szczyt',
    url='https://github.com/dszczyt/django-nested-forms',
    packages=find_packages(),
    include_package_data=True,
    classifiers=[
        "Framework :: Django",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Operating System :: OS Independent",
        "Topic :: Software Development"
    ],
)