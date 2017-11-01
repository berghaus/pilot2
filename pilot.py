#!/usr/bin/env python
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
#
# Authors:
# - Mario Lassnig, mario.lassnig@cern.ch, 2016-2017
# - Daniel Drizhuk, d.drizhuk@gmail.com, 2017
# - Paul Nilsson, paul.nilsson@cern.ch

import argparse
import logging
import sys
import threading
import time
from os import getcwd, chdir, environ

from pilot.util.constants import SUCCESS, FAILURE, ERRNO_NOJOBS
from pilot.util.https import https_setup
from pilot.util.information import set_location
from pilot.util.filehandling import get_pilot_work_dir, create_pilot_work_dir
from pilot.util.config import config

VERSION = '2017-10-31.001'


def main():
    """ Main function of PanDA Pilot 2 """

    logger = logging.getLogger(__name__)
    logger.info('PanDA Pilot 2 version %s' % VERSION)

    args.graceful_stop = threading.Event()
    config.read(args.config)

    https_setup(args, VERSION)

    if not set_location(args):
        return False

    logger.info('pilot arguments: %s' % str(args))
    logger.info('selected workflow: %s' % args.workflow)
    workflow = __import__('pilot.workflow.%s' % args.workflow, globals(), locals(), [args.workflow], -1)

    return workflow.run(args)


def import_module(workflow=None, user=None):
    pass


if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser()

    # pilot work directory
    arg_parser.add_argument('-a',
                            dest='workdir',
                            default=getcwd(),
                            help='Pilot work directory')

    # debug option to enable more log messages
    arg_parser.add_argument('-d',
                            dest='debug',
                            action='store_true',
                            default=False,
                            help='Enable debug mode for logging messages')

    # the choices must match in name the python module in pilot/workflow/
    arg_parser.add_argument('-w',
                            dest='workflow',
                            default='generic',
                            choices=['generic', 'generic_hpc',
                                     'production', 'production_hpc',
                                     'analysis', 'analysis_hpc',
                                     'eventservice', 'eventservice_hpc'],
                            help='Pilot workflow (default: generic)')

    # graciously stop pilot process after hard limit
    arg_parser.add_argument('-l',
                            dest='lifetime',
                            default=3600,
                            type=int,
                            help='Pilot lifetime seconds (default: 3600 s)')

    # set the appropriate site, resource and queue
    arg_parser.add_argument('-q',
                            dest='queue',
                            required=True,
                            help='MANDATORY: queue name (e.g., AGLT2_TEST-condor')
    arg_parser.add_argument('-r',
                            dest='resource',
                            required=True,  # it is needed by the dispatcher (only)
                            help='MANDATORY: resource name (e.g., AGLT2_TEST')
    arg_parser.add_argument('-s',
                            dest='site',
                            required=True,  # it is needed by the dispatcher (only)
                            help='MANDATORY: site name (e.g., AGLT2_TEST')

    # graciously stop pilot process after hard limit
    arg_parser.add_argument('-j',
                            dest='job_label',
                            default='ptest',
                            help='Job prod/source label (default: ptest)')

    # SSL certificates
    arg_parser.add_argument('--cacert',
                            dest='cacert',
                            default=None,
                            help='CA certificate to use with HTTPS calls to server, commonly X509 proxy',
                            metavar='path/to/your/certificate')
    arg_parser.add_argument('--capath',
                            dest='capath',
                            default=None,
                            help='CA certificates path',
                            metavar='path/to/certificates/')

    # PanDA server URL and port
    arg_parser.add_argument('--url',
                            dest='url',
                            default='',  # the proper default is stored in config.cfg
                            help='PanDA server URL')
    arg_parser.add_argument('-p',
                            dest='port',
                            default=25443,
                            help='PanDA server port')

    # Configuration option
    arg_parser.add_argument('--config',
                            dest='config',
                            default='',
                            help='Config file path',
                            metavar='path/to/pilot.cfg')

    # Country group
    arg_parser.add_argument('--country-group',
                            dest='country_group',
                            default='',
                            help='Country group option for getjob request')

    # Working group
    arg_parser.add_argument('--working-group',
                            dest='working_group',
                            default='',
                            help='Working group option for getjob request')

    # Allow other country
    arg_parser.add_argument('--allow-other-country',
                            dest='allow_other_country',
                            type=bool,
                            default=False,
                            help='Is the resource allowed to be used outside the privileged group?')

    # Allow same user
    arg_parser.add_argument('--allow-same-user',
                            dest='allow_same_user',
                            type=bool,
                            default=True,
                            help='Multi-jobs will only come from same taskID (and thus same user)')

    # Experiment
    arg_parser.add_argument('--pilot-user',
                            dest='pilot_user',
                            default='generic',
                            required=True,
                            help='Pilot user, e.g. name of experiment')

    args = arg_parser.parse_args()

    # Create the main pilot workdir and cd into it
    mainworkdir = get_pilot_work_dir(args.workdir)
    try:
        create_pilot_work_dir(mainworkdir)
    except Exception as e:
        # print to stderr since logging has not been established yet
        from sys import stderr
        print >> stderr, 'failed to create workdir at %s -- aborting: %s' % (mainworkdir, e)
        sys.exit(FAILURE)
    else:
        environ['PILOT_HOME'] = mainworkdir  # TODO: replace with singleton
        args.mainworkdir = mainworkdir
        chdir(mainworkdir)

    # Set the pilot user
    environ['PILOT_USER'] = args.pilot_user  # TODO: replace with singleton

    # Establish logging
    console = logging.StreamHandler(sys.stdout)
    if args.debug:
        logging.basicConfig(filename='pilotlog.txt', level=logging.DEBUG,
                            format='%(asctime)s | %(levelname)-8s | %(threadName)-10s | %(name)-32s | %(funcName)-32s | %(message)s')
        logging.Formatter.converter = time.gmtime
        console.setLevel(logging.DEBUG)
        console.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-8s | %(threadName)-10s | %(name)-32s | %(funcName)-32s | %(message)s'))
    else:
        logging.basicConfig(filename='pilotlog.txt', level=logging.INFO,
                            format='%(asctime)s | %(levelname)-8s | %(message)s')
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s'))
    logging.getLogger('').addHandler(console)

    trace = main()
    logging.shutdown()

    if not trace:
        logging.getLogger(__name__).critical('pilot startup did not succeed -- aborting')
        sys.exit(FAILURE)
    elif trace.pilot['nr_jobs'] > 0:
        sys.exit(SUCCESS)
    else:
        sys.exit(ERRNO_NOJOBS)
