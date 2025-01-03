import setuptools
from pathlib import Path

readme_file = Path('README.md')
readme_text = readme_file.read_text()

setuptools.setup(
    name='sqlog',
    version='2.0',
    license='MIT',
    url='https://github.com/andriystr/sqlog',
    author='Andriy Stremeluk',
    author_email='astremeluk@gmail.com',
    description='Hierarchical logging',
    long_description=readme_text,
    long_description_content_type='text/markdown',
    py_modules=['sqlog'],
    classifiers=[
        'Programming Language :: Python :: 3.7',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent'
    ],
    python_requires='>=3.7',
    entry_points={
        'console_scripts': [
            'sqlog = sqlog:main',
        ]
    }
)
