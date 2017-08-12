# economist-ebook

This little script downloads and parses the weekly print edition from The Economist, and builds an ebook in `epub` format.


### Install

You need Python3. Assuming you are in a `virtualenv`, use `python`, and `pip` in the following commands. Replace them with `python3` and `pip3` if your system-wide Python installation is 2.X.

NOTE: You will still most likely need to install the following libraries via your package manager:

* PIL: libjpeg-dev zlib1g-dev libpng12-dev
* lxml: libxml2-dev libxslt-dev
* Python Development version: python-dev

Once the above dependencies are satisfied:

        $ pip install -r requirements.txt


### Usage

        $ python economist.py

This will fetch the latest print edition and build the ebook. Upon feching the issue, you'll see some metadata like issue number, section names, and article count. Give some time for all articles and images to download if this is the first time the issue is downloaded.

The resulting `epub` will be placed in the same directory, named `the_economist_YYYY-MM-DD.epub`, where `YYYY-MM-DD` represents the issue date.

The articles are cached in a SQLite database, which is meant to limit the number of requests made to The Economist.

### License

This software is distributed under the BSD-style license found in the LICENSE file.
