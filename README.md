Gengo Gettext
=============

Create Gengo translation jobs using a gettext catalog or JSON files.

## Getting Started

* Install `requirements.txt`, requires python 2.7
  * `build-virtualenv`
  * `. virtualenv/bin/activate`
* Create a `configuration.json`
  * configure against `production` to place orders (`configurator gengo-gettext production -l`)
  * any other env will use gengo's sandbox
* Configure projects
  * `cp projects.sample.ini projects.ini`
* Run `./gengogettext.py`

## Projects configuration

We use two i18n approaches in our applications: gettext and JSON based translations.

Every project, no matter which i18n approach it uses, can be configured with the following options:
* `languages` - (_string_) a list of languages separated by space
* `edit_jobs` - (_boolean_) if truthy, additional ["Edit" service](https://support.gengo.com/hc/en-us/articles/360001123788-What-are-Edit-jobs-) will be ordered for each job

Configuration options required by gettext projects:
* `domains` - (_string_) a list of gettext domains separated by space
* `<domain-name>` - (_string_) an absolute directory path where .po file for given domain is stored

Configuration option required by projects with JSON i18n approach:
* `locale_dir` - (_string_) an absolute directory path where JSON files with source strings and translations are stored
