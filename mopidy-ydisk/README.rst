************
Mopidy-YDisk
************

.. image:: https://img.shields.io/pypi/v/Mopidy-YDisk.svg?style=flat
    :target: https://pypi.python.org/pypi/Mopidy-YDisk/
    :alt: Latest PyPI version

`Mopidy <http://www.mopidy.com/>`_ extension for playing music files from `Yandex.Disk <https://disk.yandex.ru/>`_.


Installation
============

Install by running::

    sudo pip install Mopidy-YDisk

Or, if available, install the Debian/Ubuntu package from `apt.mopidy.com <http://apt.mopidy.com/>`_.


Configuration
=============

Before starting Mopidy, you must acquire and add Yandex.Disk tokens to your Mopidy configuration file::

    [ydisk]
    tokens = <token_1>, ..., <token_n>


To acquire a Yandex.Disk token, use Mopidy commands::

    mopidy ydisk shortlink
    mopidy ydisk token <auth_code>


Project resources
=================

- `Source code <https://github.com/vonZeppelin/mopidy-ydisk>`_
- `Issue tracker <https://github.com/vonZeppelin/mopidy-ydisk/issues>`_


Credits
=======

- Original author: `Leonid Bogdanov <https://github.com/vonZeppelin>`_
- Current maintainer: `Leonid Bogdanov <https://github.com/vonZeppelin>`_


Changelog
=========

v0.1.0
----------------------------------------

- Initial release.
