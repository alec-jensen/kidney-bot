import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

import aiohttp
from PIL import Image

from .error import InvalidImageUrl


class Meme:
    __slots__ = ('avatar',)

    def __init__(self, avatar: str):
        self.avatar = avatar

    @staticmethod
    async def _image(url: str) -> Image.Image:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise InvalidImageUrl(f"Invalid image url: {url}")
                data = await response.read()
                return Image.open(BytesIO(data))

    async def fight_under_this_flag(self) -> BytesIO:
        path = str(Path(__file__).parent)

        avatar: Image.Image
        if isinstance(self.avatar, str) and self.avatar.startswith("http"):
            avatar = await Meme._image(self.avatar)
        elif isinstance(self.avatar, Image.Image):
            avatar = self.avatar
        else:
            raise TypeError(f"avatar must be a url, not {type(self.avatar)}")

        def _process(av: Image.Image, p: str) -> BytesIO:
            av = av.resize((197, 197))
            background = Image.open(p + "/assets/fight.jpeg")
            overlay2 = Image.open(p + "/assets/overlay2.png").resize((197, 197))
            nw = Image.new("RGBA", (197, 197))
            nw.paste(av, (0, 0), overlay2.convert("L"))
            nw = nw.rotate(7, expand=True)
            background.paste(nw, (570, 34), nw)
            overlay3 = Image.open(p + "/assets/overlay3.png").resize((284, 284))
            nw = Image.new("RGBA", (284, 284))
            nw.paste(av.resize((284, 284)), (0, 0), overlay3.convert("L"))
            nw = nw.rotate(10, expand=True)
            background.paste(nw, (-1, 347), nw)
            overlay4 = Image.open(p + "/assets/overlay4.png").resize((294, 294))
            nw = Image.new("RGBA", (294, 294))
            nw.paste(av.resize((294, 294)), (0, 0), overlay4.convert("L"))
            nw = nw.rotate(10, expand=True)
            background.paste(nw, (394, 271), nw)
            image = BytesIO()
            background.save(image, 'PNG')
            image.seek(0)
            return image

        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            return await loop.run_in_executor(pool, _process, avatar, path)

    async def uwu_discord(self) -> BytesIO:
        path = str(Path(__file__).parent)

        avatar: Image.Image
        if isinstance(self.avatar, str) and self.avatar.startswith("http"):
            avatar = await Meme._image(self.avatar)
        elif isinstance(self.avatar, Image.Image):
            avatar = self.avatar
        else:
            raise TypeError(f"avatar must be a url, not {type(self.avatar)}")

        def _process(av: Image.Image, p: str) -> BytesIO:
            av = av.resize((500, 500))
            uwu = Image.open(p + "/assets/uwu_mask.png")
            back = Image.new("RGBA", (500, 500))
            back.paste(av, (0, 0), uwu.convert("L"))
            image = BytesIO()
            back.save(image, 'PNG')
            image.seek(0)
            return image

        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            return await loop.run_in_executor(pool, _process, avatar, path)

    async def rip(self) -> BytesIO:
        path = str(Path(__file__).parent)

        avatar: Image.Image
        if isinstance(self.avatar, str) and self.avatar.startswith("http"):
            avatar = await Meme._image(self.avatar)
        elif isinstance(self.avatar, Image.Image):
            avatar = self.avatar
        else:
            raise TypeError(f"avatar must be a url, not {type(self.avatar)}")

        def _process(av: Image.Image, p: str) -> BytesIO:
            av = av.resize((521 // 2, 620 // 2))
            mask_im = Image.open(p + "/assets/rip.png").convert('L').resize((521 // 2, 620 // 2))
            background = Image.open(p + "/assets/rip.png").resize((521 // 2, 620 // 2))
            background.paste(av, (0, 0), mask_im)
            image = BytesIO()
            background.save(image, 'PNG')
            image.seek(0)
            return image

        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            return await loop.run_in_executor(pool, _process, avatar, path)
