from __future__ import absolute_import, division, unicode_literals

import logging

import mutagen
import pykka

from datetime import timedelta
from itertools import cycle

from cachetools import TTLCache
from furl import furl
from mopidy import backend
from mopidy.models import Album, Artist, Ref, Track
from six import iterkeys, itervalues
from six.moves import range

from . import Extension, get_proxy, get_user_agent
from .ydisk import YDisk, YDiskDirectory


logger = logging.getLogger(__name__)

ROOT_URI = 'ydisk:/'


class TagsRetriever(pykka.ThreadingActor):

    def __init__(self, parent_ref):
        super(TagsRetriever, self).__init__()

        self.parent_ref = parent_ref

    def on_receive(self, message):
        file_uri = message['file_uri']
        file_supplier = message['file_supplier']
        tags = mutagen.File(file_supplier(), easy=True)
        if tags:
            logger.debug('Read tags for file %s: %s', file_uri, tags)
            self.parent_ref.tell({
                'file_uri': file_uri,
                'tags': tags
            })


class TagsReader(pykka.ThreadingActor):

    def __init__(self):
        super(TagsReader, self).__init__()

        tag_retrieving_concurrency = 5
        cache_ttl = timedelta(hours=12).total_seconds()
        self.cache = TTLCache(maxsize=1000, ttl=cache_ttl)
        self.tags_retriever_indexer = cycle(
            range(tag_retrieving_concurrency)
        )
        self.tags_retrievers = [
            TagsRetriever.start(self.actor_ref)
            for _ in range(tag_retrieving_concurrency)
        ]

    def on_stop(self):
        for ref in self.tags_retrievers:
            ref.stop()
        self.cache.clear()

    def on_receive(self, message):
        self.cache[message['file_uri']] = message['tags']

    def read(self, file_uri, file_supplier):
        tags = self.cache.get(file_uri)
        if not tags:
            logger.debug('No cached tags for file %s, reading...', file_uri)
            tags_retriever_idx = next(self.tags_retriever_indexer)
            tags_retriever_ref = self.tags_retrievers[tags_retriever_idx]
            tags_retriever_ref.tell({
                'file_uri': file_uri,
                'file_supplier': file_supplier
            })
        return tags


class YDiskBackend(pykka.ThreadingActor, backend.Backend):

    uri_schemes = [Extension.ext_name]

    def __init__(self, config, audio):
        super(YDiskBackend, self).__init__()

        self.tags_reader_ref = TagsReader.start()
        self.library = YDiskLibrary(
            backend=self,
            tags_reader=self.tags_reader_ref.proxy(),
            proxy=get_proxy(config),
            tokens=config[Extension.ext_name]['tokens']
        )
        self.playback = YDiskPlayback(audio=audio, backend=self)

    def on_start(self):
        self.library.init()

    def on_stop(self):
        self.library.dispose()
        self.tags_reader_ref.stop()


class YDiskLibrary(backend.LibraryProvider):

    discs = {}
    root_directory = Ref.directory(uri=ROOT_URI, name='Yandex.Disk')

    def __init__(self, backend, tags_reader, proxy, tokens):
        super(YDiskLibrary, self).__init__(backend)

        def init():
            user_agent = get_user_agent()
            self.discs = {
                disc.id: disc
                for disc in (
                    YDisk(token=token, proxy=proxy, user_agent=user_agent)
                    for token in tokens
                )
            }
            logger.info(
                'Initialized YDisks [%s]', ', '.join(iterkeys(self.discs))
            )

        self.init = init
        self.tags_reader = tags_reader

    def browse(self, uri):
        if uri == ROOT_URI:
            return [
                Ref.directory(uri=ROOT_URI + disc.id, name=disc.name)
                for disc in itervalues(self.discs)
            ]
        else:
            disc_id, _, dir_path = YDiskLibrary._resource_coords(uri)
            disc = self.discs[disc_id]
            return [
                YDiskLibrary._make_ref(disc_id, resource)
                for resource in disc.browse_dir(dir_path)
            ]

    def lookup(self, uri):
        disc_id, file_name, file_path = YDiskLibrary._resource_coords(uri)
        disc = self.discs[disc_id]
        file_tags_future = self.tags_reader.read(
            uri, lambda: disc.get_file(file_path)
        )
        file_tags = file_tags_future.get()
        if file_tags:
            return [
                Track(
                    uri=uri,
                    name=YDiskLibrary._get_tag(file_tags, 'title', file_name),
                    artists=[
                        Artist(name=artist, sortname=artist)
                        for artist in file_tags.get('artist', ())
                    ],
                    album=Album(
                        name=YDiskLibrary._get_tag(file_tags, 'album')
                    ),
                    genre=YDiskLibrary._get_tag(file_tags, 'genre'),
                    track_no=int(
                        YDiskLibrary._get_tag(file_tags, 'tracknumber', 0)
                    ),
                    disc_no=int(
                        YDiskLibrary._get_tag(file_tags, 'discnumber', 0)
                    ),
                    date=YDiskLibrary._get_tag(file_tags, 'date'),
                    bitrate=int(
                        YDiskLibrary._get_tag(file_tags, 'bpm', 0)
                    )
                )
            ]
        else:
            return [Track(uri=uri, name=file_name)]

    def dispose(self):
        for disc in itervalues(self.discs):
            disc.dispose()

    @staticmethod
    def _get_tag(tags, tag_key, default='Unknown'):
        return next(
            iter(tags.get(tag_key) or ()), default
        )

    @staticmethod
    def _resource_coords(resource_uri):
        path = furl(resource_uri).path
        name = path.segments[-1]
        disc_id = path.segments.pop(0)
        return disc_id, name, '/'.join(path.segments) or '/'

    @staticmethod
    def _make_ref(disc_id, resource):
        resource_uri = (furl(ROOT_URI) / disc_id / resource.path).url
        if isinstance(resource, YDiskDirectory):
            return Ref.directory(uri=resource_uri, name=resource.name)
        else:
            return Ref.track(uri=resource_uri, name=resource.name)


class YDiskPlayback(backend.PlaybackProvider):

    def translate_uri(self, uri):
        disc_id, _, file_path = YDiskLibrary._resource_coords(uri)
        disc = self.backend.library.discs[disc_id]

        return disc.get_file(file_path).file_path
