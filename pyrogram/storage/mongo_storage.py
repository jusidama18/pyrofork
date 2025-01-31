import asyncio
import inspect
import time
from typing import List, Tuple, Any

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne
from pyrogram.storage.storage import Storage
from pyrogram.storage.sqlite_storage import get_input_peer


class MongoStorage(Storage):
    """
    Initializes a new session.

    Parameters:
        - name (str): The session name used for database name.
        - remove_peers (bool): Flag to remove data in the peers collection. If set to True, 
                               the data related to peers will be removed everytime client log out. 
                               If set to False or None, the data will not be removed.
        - **kwargs: Additional keyword arguments to pass to the AsyncIOMotorClient.

    Note:
        The `kwargs` parameter is used to pass additional arguments to the underlying AsyncIOMotorClient
        instance. Refer to the AsyncIOMotorClient documentation for the list of available arguments.

    Example:
        session = MongoStorage("my_session", remove_peers=True, uri="mongodb://...")
    """
    lock: asyncio.Lock
    USERNAME_TTL = 8 * 60 * 60

    def __init__(self, name: str, remove_peers: bool = None, **kwargs):
        super().__init__(name=name)
        database = AsyncIOMotorClient(**kwargs)[name]
        self.lock = asyncio.Lock()
        self.database = database
        self._peer = database['peers']
        self._session = database['session']
        self._remove_peers = remove_peers or False

    async def open(self):
        """

        dc_id     INTEGER PRIMARY KEY,
        api_id    INTEGER,
        test_mode INTEGER,
        auth_key  BLOB,
        date      INTEGER NOT NULL,
        user_id   INTEGER,
        is_bot    INTEGER
        """
        if await self._session.find_one({'_id': 0}, {}):
            return
        await self._session.insert_one(
            {
                '_id': 0,
                'dc_id': 2,
                'api_id': None,
                'test_mode': None,
                'auth_key': b'',
                'date': 0,
                'user_id': 0,
                'is_bot': 0,

            }
        )

    async def save(self):
        pass

    async def close(self):
        pass

    async def delete(self):
        try:
            await self._session.delete_one({'_id': 0})
            if self._remove_peers:
                await self._peer.remove({})
        except Exception as _:
            return

    async def update_peers(self, peers: List[Tuple[int, int, str, str, str]]):
        """(id, access_hash, type, username, phone_number)"""
        s = int(time.time())
        bulk = [
            UpdateOne(
                {'_id': i[0]},
                {'$set': {
                    'access_hash': i[1], 
                    'type': i[2], 
                    'username': i[3], 
                    'phone_number': i[4],
                    'last_update_on': s
                }},
                upsert=True
            ) for i in peers
        ]
        if not bulk:
            return
        await self._peer.bulk_write(
            bulk
        )

    async def get_peer_by_id(self, peer_id: int):
        # id, access_hash, type
        r = await self._peer.find_one({'_id': peer_id}, {'_id': 1, 'access_hash': 1, 'type': 1})
        if not r:
            raise KeyError(f"ID not found: {peer_id}")
        return get_input_peer(r['_id'], r['access_hash'], r['type'])

    async def get_peer_by_username(self, username: str):
        # id, access_hash, type, last_update_on,
        r = await self._peer.find_one({'username': username},
                                      {'_id': 1, 'access_hash': 1, 'type': 1, 'last_update_on': 1})

        if r is None:
            raise KeyError(f"Username not found: {username}")

        if abs(time.time() - r['last_update_on']) > self.USERNAME_TTL:
            raise KeyError(f"Username expired: {username}")

        return get_input_peer(r['_id'], r['access_hash'], r['type'])

    async def get_peer_by_phone_number(self, phone_number: str):

        #  _id, access_hash, type,
        r = await self._peer.find_one({'phone_number': phone_number},
                                      {'_id': 1, 'access_hash': 1, 'type': 1})

        if r is None:
            raise KeyError(f"Phone number not found: {phone_number}")

        return get_input_peer(r['_id'], r['access_hash'], r['type'])

    async def _get(self):
        attr = inspect.stack()[2].function
        d = await self._session.find_one({'_id': 0}, {attr: 1})
        if not d:
            return
        return d[attr]

    async def _set(self, value: Any):
        attr = inspect.stack()[2].function
        await self._session.update_one({'_id': 0}, {'$set': {attr: value}}, upsert=True)

    async def _accessor(self, value: Any = object):
        return await self._get() if value == object else await self._set(value)

    async def dc_id(self, value: int = object):
        return await self._accessor(value)

    async def api_id(self, value: int = object):
        return await self._accessor(value)

    async def test_mode(self, value: bool = object):
        return await self._accessor(value)

    async def auth_key(self, value: bytes = object):
        return await self._accessor(value)

    async def date(self, value: int = object):
        return await self._accessor(value)

    async def user_id(self, value: int = object):
        return await self._accessor(value)

    async def is_bot(self, value: bool = object):
        return await self._accessor(value)
