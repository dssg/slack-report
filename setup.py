import pathlib

from setuptools import setup


README_PATH = pathlib.Path(__file__).parent / 'README.adoc'


setup(
    name='slack-report',
    version='0.1.0',
    description="report output of command to slack channel",
    long_description=README_PATH.read_text(),
    # don't worry about rendering content for now
    long_description_content_type='text/plain',
    author="Jesse London",
    author_email='jesselondon@gmail.com',
    license='BSD 3-Clause',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Natural Language :: English',
        'Programming Language :: Python :: 3.7',
    ],
    url="https://github.com/dssg/slack-report",
    python_requires='>=3.7',
    package_dir={'': 'src'},
    py_modules=['slack_report'],
    install_requires=[
        'argcmdr==0.6.0',
        'requests==2.22.0',
    ],
    entry_points={
        'console_scripts': [
            'slack-report = slack_report:main',
        ],
    },
)
