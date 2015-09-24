from setuptools import setup, find_packages
import sys, os

version = '0.0'

setup(name='wwproxy',
      version=version,
      description="Proxy WebSocket to WAMP",
      long_description="""\
""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='',
      author='Petri Savolainen',
      author_email='petri.savolainen@koodaamo.fi',
      url='',
      license='GPL',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests'])+["twisted.plugins"],
      include_package_data=True,
      zip_safe=False,
      install_requires=[
          # -*- Extra requirements: -*-
      ],
      entry_points="""
      # -*- Entry points: -*-
      """,
      )
