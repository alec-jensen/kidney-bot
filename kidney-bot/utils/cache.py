import asyncio
import time
import logging
import sys

from utils.misc import humanbytes

class Cache:
    def __init__(self, ttl: int = 60, cleanup_interval: int | None = None):
            """
            Initializes a Cache object.

            Args:
                ttl (int): Time-to-live for cache entries in seconds. Defaults to 60.
                cleanup_interval (int): Interval in seconds between cache cleanups. Defaults to ttl value.
            """

            self._storage = []
            self._ttl = ttl
            self._last_cleanup = time.time()
            if cleanup_interval is None:
                self._cleanup_interval = ttl
            else:
                self._cleanup_interval = cleanup_interval

    """
    CacheItem = {
        value: obj value
        time_created: time, in seconds, of object creation
    }
    """

    async def add(self, obj):
        if not isinstance(obj, dict):
            raise TypeError("obj must be a dict")
        
        if await self.get_one(obj) is not None:
            return
        
        cacheItem = {"value": obj, "time_created": time.time()}
        
        self._storage.append(cacheItem)

    async def add_many(self, objs):
        for obj in objs:
            await self.add(obj)

    async def get_one(self, query):
        for item in self._storage:
            for key, value in query.items():
                if item['value'][key] != value:
                    break
            else:
                return item['value']

        return None

    async def get_all(self, query, limit=None):
        if limit is None:
            limit = len(self._storage)

        results = []

        for item in self._storage:
            for key, value in query.items():
                if item['value'][key] != value:
                    break
            else:
                results.append(item['value'])

        if results == []:
            return None
        elif len(results) <= limit:
            return results
        else:
            return results[:limit]
        
    async def count(self, query):
        count = 0

        for item in self._storage:
            for key, value in query.items():
                if item['value'][key] != value:
                    break
            else:
                count += 1

        return count
    
    async def remove(self, query):
        obj = await self.get_one(query)
        if obj is None:
            return
        
        for i, item in enumerate(self._storage):
            if item['value'] == obj:
                self._storage.pop(i)
                break

    async def remove_many(self, query):
        objs = await self.get_all(query)
        if objs is None:
            return
        
        for obj in objs:
            await self.remove(obj)

    async def update(self, query, update):
        obj = await self.get_one(query)
        if obj is None:
            return
        
        new_obj = obj.copy()
        for key, value in update["$set"].items():
            new_obj[key] = value

        await self.remove(query)
        await self.add(new_obj)
    
    async def clear(self):
        self._storage = []

    async def _cleanup(self):
        self._last_cleanup = time.time()

        start_len = len(self._storage)
        start_size = sys.getsizeof(self._storage)

        self._storage = [item for item in self._storage if time.time() - item['time_created'] <= self._ttl]

        end_len = len(self._storage)
        end_size = sys.getsizeof(self._storage)

        if start_len - end_len > 0:
            logging.info(f'Cache cleanup complete. Removed {start_len - end_len} items ({
                humanbytes(start_size-end_size)}). Took {time.time() - self._last_cleanup} seconds.')

    async def cleanup_task(self):
        """
        A background task that runs cache cleanup at regular intervals.
        """
        while True:
            if time.time() - self._last_cleanup >= self._cleanup_interval:
                await self._cleanup()
            elif sys.getsizeof(self._storage) > 1024 * 1024 * 1024: # 1 GB
                await self.clear()
                logging.info('Cache cleared due to size limit.')
            
            time_until_next_cleanup = self._cleanup_interval - (time.time() - self._last_cleanup)
            await asyncio.sleep(time_until_next_cleanup)
