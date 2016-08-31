Gengo Gettext
=============

Create Gengo translation jobs using a gettext catalog.

## Getting Started

* Install `requirements.txt`, requires python 2.7
* Create a `configuration.json`
  * configure against `production` to place orders
  * any other env will use gengo's sandbox
* Configure projects
  * `cp projects.sample.ini projects.ini`
* Run `./gengogettext.py`
