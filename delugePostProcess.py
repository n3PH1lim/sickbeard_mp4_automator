#!/usr/bin/env python

import os
import sys
from autoprocess import autoProcessTV, autoProcessMovie, autoProcessTVSR, sonarr, radarr
from resources.readsettings import ReadSettings
from resources.mediaprocessor import MediaProcessor
from resources.log import getLogger
from deluge_client import DelugeRPCClient
import shutil

log = getLogger("DelugePostProcess")

log.info("Deluge post processing started.")

try:
    settings = ReadSettings()
    categories = [settings.deluge['sb'], settings.deluge['cp'], settings.deluge['sonarr'], settings.deluge['radarr'], settings.deluge['sr'], settings.deluge['bypass']]
    remove = settings.deluge['remove']

    if len(sys.argv) < 4:
        log.error("Not enough command line parameters present, are you launching this from deluge?")
        sys.exit(1)

    path = str(sys.argv[3])
    torrent_name = str(sys.argv[2])
    torrent_id = str(sys.argv[1])
    delete_dir = None

    log.debug("Path: %s." % path)
    log.debug("Torrent: %s." % torrent_name)
    log.debug("Hash: %s." % torrent_id)

    client = DelugeRPCClient(host=settings.deluge['host'], port=int(settings.deluge['port']), username=settings.deluge['user'], password=settings.deluge['pass'])
    client.connect()

    if client.connected:
        log.info("Successfully connected to Deluge")
    else:
        log.error("Failed to connect to Deluge")
        sys.exit(1)

    torrent_data = client.call('core.get_torrent_status', torrent_id, ['files', 'label'])
    try:
        torrent_files = torrent_data[b'files']
        category = torrent_data[b'label'].lower().decode()
    except:
        torrent_files = torrent_data['files']
        category = torrent_data['label'].lower()

    files = []
    log.debug("List of files in torrent:")
    for contents in torrent_files:
        try:
            files.append(contents[b'path'].decode())
            log.debug(contents[b'path'].decode())
        except:
            files.append(contents['path'])
            log.debug(contents['path'])

    if category not in categories:
        log.error("No valid category detected.")
        sys.exit(1)

    if len(categories) != len(set(categories)):
        log.error("Duplicate category detected. Category names must be unique.")
        sys.exit(1)

    try:
        if settings.deluge['convert']:
            # Check for custom Deluge output_dir
            if settings.deluge['output_dir']:
                settings.output_dir = settings.deluge['output_dir']
                log.debug("Overriding output_dir to %s." % settings.deluge['output_dir'])

            # Perform conversion.
            settings.delete = False
            if not settings.output_dir:
                suffix = "convert"
                settings.output_dir = os.path.join(path, ("%s-%s" % (torrent_name, suffix)))
            else:
                settings.output_dir = os.path.join(settings.output_dir, torrent_name)
            if not os.path.exists(settings.output_dir):
                try:
                    os.makedirs(settings.output_dir)
                    delete_dir = settings.output_dir
                except:
                    log.exception("Unable to make output directory %s." % settings.output_dir)

            mp = MediaProcessor(settings)

            if len(files) < 1:
                log.error("No files provided by torrent")

            for filename in files:
                inputfile = os.path.join(path, filename)
                info = mp.isValidSource(inputfile)
                if info:
                    log.info("Converting file %s at location %s." % (inputfile, settings.output_dir))
                    try:
                        output = mp.process(inputfile, info=info)
                    except:
                        log.exception("Error converting file %s." % inputfile)

            path = settings.output_dir
        else:
            suffix = "copy"
            newpath = os.path.join(path, ("%s-%s" % (torrent_name, suffix)))
            if not os.path.exists(newpath):
                try:
                    os.mkdir(newpath)
                except:
                    log.exception("Unable to make copy directory %s." % newpath)
            for filename in files:
                inputfile = os.path.join(path, filename)
                log.info("Copying file %s to %s." % (inputfile, newpath))
                shutil.copy(inputfile, newpath)
            path = newpath
            delete_dir = newpath
    except:
        log.exception("Error occurred handling file")

    # Send to Sickbeard
    if (category == categories[0]):
        log.info("Passing %s directory to Sickbeard." % path)
        autoProcessTV.processEpisode(path, settings)
    # Send to CouchPotato
    elif (category == categories[1]):
        log.info("Passing %s directory to Couch Potato." % path)
        autoProcessMovie.process(path, settings, torrent_name)
    # Send to Sonarr
    elif (category == categories[2]):
        log.info("Passing %s directory to Sonarr." % path)
        sonarr.processEpisode(path, settings)
    elif (category == categories[3]):
        log.info("Passing %s directory to Radarr." % path)
        radarr.processMovie(path, settings)
    elif (category == categories[4]):
        log.info("Passing %s directory to Sickrage." % path)
        autoProcessTVSR.processEpisode(path, settings)
    elif (category == categories[5]):
        log.info("Bypassing any further processing as per category.")

    if delete_dir:
        if os.path.exists(delete_dir):
            try:
                os.rmdir(delete_dir)
                log.debug("Successfully removed tempoary directory %s." % delete_dir)
            except:
                log.exception("Unable to delete temporary directory.")

    if remove:
        try:
            client.call('core.remove_torrent', torrent_id, True)
        except:
            log.exception("Unable to remove torrent from deluge.")
    sys.exit(0)
except:
    log.exception("Unexpected exception.")
    sys.exit(1)
