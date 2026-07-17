import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BufferedIOBase, BytesIO, IOBase
from os import PathLike
from pathlib import Path

import aiohttp
from PIL import Image, ImageDraw, ImageFont

from .error import InvalidImageType, InvalidImageUrl


class CardSettings:
    __slots__ = ('background', 'background_color', 'bar_color', 'text_color')

    def __init__(
        self,
        background: PathLike | BufferedIOBase | str | None = None,
        background_color: str | None = "#36393f",
        bar_color: str | None = 'white',
        text_color: str | None = 'white',
    ) -> None:
        self.background = background
        self.bar_color = bar_color
        self.text_color = text_color
        self.background_color = background_color


class RankCard:
    __slots__ = (
        'avatar',
        'background',
        'background_color',
        'bar_color',
        'current_exp',
        'level',
        'max_exp',
        'rank',
        'settings',
        'text_color',
        'username',
    )

    def __init__(
        self,
        settings: CardSettings,
        avatar: str,
        level: int,
        username: str,
        current_exp: int,
        max_exp: int,
        rank: int | None = None,
    ) -> None:
        self.background = settings.background
        self.background_color = settings.background_color
        self.avatar = avatar
        self.level = level
        self.rank = rank
        self.username = username
        self.current_exp = current_exp
        self.max_exp = max_exp
        self.bar_color = settings.bar_color
        self.text_color = settings.text_color

    @staticmethod
    def _convert_number(number: int) -> str:
        if number >= 1_000_000_000:
            return f"{number / 1_000_000_000:.1f}B"
        elif number >= 1_000_000:
            return f"{number / 1_000_000:.1f}M"
        elif number >= 1_000:
            return f"{number / 1_000:.1f}K"
        else:
            return str(number)

    @staticmethod
    async def _image(url: str) -> Image.Image:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise InvalidImageUrl(f"Invalid image url: {url}")
                data = await response.read()
                return Image.open(BytesIO(data))

    async def _load_background(self) -> Image.Image:
        if isinstance(self.background, IOBase):
            if not (self.background.seekable() and self.background.readable()):
                raise InvalidImageType(f"File buffer {self.background!r} must be seekable and readable and in binary mode")
            return Image.open(self.background)
        elif isinstance(self.background, str):
            if self.background.startswith("http"):
                return await RankCard._image(self.background)
            else:
                return Image.open(open(self.background, "rb"))
        elif isinstance(self.background, Image.Image):
            return self.background
        else:
            raise InvalidImageType(f"background must be a path or url or a file buffer, not {type(self.background)}")

    async def _load_avatar(self) -> Image.Image:
        if isinstance(self.avatar, str):
            if self.avatar.startswith("http"):
                return await RankCard._image(self.avatar)
        if isinstance(self.avatar, Image.Image):
            return self.avatar
        raise TypeError(f"avatar must be a url, not {type(self.avatar)}")

    async def card1(self) -> BytesIO:
        path = str(Path(__file__).parent)
        bg = await self._load_background()
        av = await self._load_avatar()
        text_color = self.text_color
        bar_color = self.bar_color
        current_exp = self.current_exp
        max_exp = self.max_exp
        level = self.level
        username = self.username

        def _process(background: Image.Image, avatar: Image.Image) -> BytesIO:
            avatar = avatar.resize((170, 170))
            overlay = Image.open(path + "/assets/overlay1.png")
            bg_out = Image.new("RGBA", overlay.size)
            bg_out.paste(background.resize((638, 159)), (0, 0))
            bg_out = bg_out.resize(overlay.size)
            bg_out.paste(overlay, (0, 0), overlay)

            font40 = ImageFont.truetype(path + "/assets/levelfont.otf", 40)
            font30 = ImageFont.truetype(path + "/assets/levelfont.otf", 30)
            draw = ImageDraw.Draw(bg_out)
            draw.text((205, (327 / 2) + 20), username, font=font40, fill=text_color, stroke_width=1, stroke_fill=(0, 0, 0))

            bar_exp = max((current_exp / max_exp) * 420, 50)
            cur_str = RankCard._convert_number(current_exp)
            max_str = RankCard._convert_number(max_exp)
            draw.text((197, (327 / 2) + 125), f"LEVEL - {RankCard._convert_number(level)}", font=font30, fill=text_color, stroke_width=1, stroke_fill=(0, 0, 0))
            w = draw.textlength(f"{cur_str}/{max_str}", font=font30)
            draw.text((638 - w - 50, (327 / 2) + 125), f"{cur_str}/{max_str}", font=font30, fill=text_color, stroke_width=1, stroke_fill=(0, 0, 0))

            mask_im = Image.open(path + "/assets/mask_circle.jpg").convert('L').resize((170, 170))
            new = Image.new("RGB", avatar.size, (0, 0, 0))
            try:
                new.paste(avatar, mask=avatar.convert("RGBA").split()[3])
            except Exception:
                new.paste(avatar, (0, 0))
            bg_out.paste(new, (13, 65), mask_im)

            im = Image.new("RGB", (490, 51), (0, 0, 0))
            d = ImageDraw.Draw(im, "RGBA")
            d.rounded_rectangle((0, 0, 420, 50), 30, fill=(255, 255, 255, 50))
            d.rounded_rectangle((0, 0, bar_exp, 50), 30, fill=bar_color)
            bg_out.paste(im, (190, 235))

            new2 = Image.new("RGBA", bg_out.size)
            new2.paste(bg_out, (0, 0), Image.open(path + "/assets/curvedoverlay.png").convert("L"))
            result = new2.resize((505, 259))
            image = BytesIO()
            result.save(image, 'PNG')
            image.seek(0)
            return image

        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            return await loop.run_in_executor(pool, _process, bg, av)

    async def card2(self) -> BytesIO:
        path = str(Path(__file__).parent)
        av = await self._load_avatar()
        text_color = self.text_color
        bar_color = self.bar_color
        background_color = self.background_color
        current_exp = self.current_exp
        max_exp = self.max_exp
        level = self.level
        username = self.username
        rank = self.rank

        def _process(avatar: Image.Image) -> BytesIO:
            background = Image.new("RGB", (1000, 333), background_color)
            background.paste(Image.new("RGB", (950, 283), "#2f3136"), (25, 25))
            avatar = avatar.resize((260, 260))
            mask = Image.open(path + "/assets/curveborder.png").resize((260, 260))
            new = Image.new("RGBA", avatar.size, (0, 0, 0))
            try:
                new.paste(avatar, mask=avatar.convert("RGBA").split()[3])
            except Exception:
                new.paste(avatar, (0, 0))
            background.paste(new, (53, 73 // 2), mask.convert("L"))

            font = ImageFont.truetype(path + "/assets/levelfont.otf", 50)
            draw = ImageDraw.Draw(background)
            combined = "LEVEL: " + RankCard._convert_number(level) + (f"       RANK: {rank}" if rank is not None else "")
            w = draw.textlength(combined, font=font)
            draw.text((950 - w, 40), combined, font=font, fill=text_color, stroke_width=1, stroke_fill=(0, 0, 0))
            draw.text((330, 130), username, font=font, fill=text_color, stroke_width=1, stroke_fill=(0, 0, 0))

            exp_str = f"{RankCard._convert_number(current_exp)}/{RankCard._convert_number(max_exp)}"
            w = draw.textlength(exp_str, font=font)
            draw.text((950 - w, 130), exp_str, font=font, fill=text_color, stroke_width=1, stroke_fill=(0, 0, 0))

            bar_exp = max((current_exp / max_exp) * 619, 50)
            im = Image.new("RGB", (620, 51), "#2f3136")
            d = ImageDraw.Draw(im, "RGBA")
            d.rounded_rectangle((0, 0, 619, 50), 30, fill=(255, 255, 255, 50))
            d.rounded_rectangle((0, 0, bar_exp, 50), 30, fill=bar_color)
            background.paste(im, (330, 235))

            image = BytesIO()
            background.save(image, 'PNG')
            image.seek(0)
            return image

        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            return await loop.run_in_executor(pool, _process, av)

    async def card3(self) -> BytesIO:
        path = str(Path(__file__).parent)
        bg = await self._load_background()
        av = await self._load_avatar()
        text_color = self.text_color
        bar_color = self.bar_color
        current_exp = self.current_exp
        max_exp = self.max_exp
        level = self.level
        username = self.username
        rank = self.rank

        def _process(background: Image.Image, avatar: Image.Image) -> BytesIO:
            background = background.resize((1000, 333))
            cut = Image.new("RGBA", (950, 283), (0, 0, 0, 200))
            background.paste(cut, (25, 25), cut)
            avatar = avatar.resize((260, 260))
            mask = Image.open(path + "/assets/curveborder.png").resize((260, 260))
            new = Image.new("RGBA", avatar.size, (0, 0, 0))
            try:
                new.paste(avatar, mask=avatar.convert("RGBA").split()[3])
            except Exception:
                new.paste(avatar, (0, 0))
            background.paste(new, (53, 73 // 2), mask.convert("L"))

            font = ImageFont.truetype(path + "/assets/levelfont.otf", 50)
            draw = ImageDraw.Draw(background)
            combined = "LEVEL: " + RankCard._convert_number(level) + (f"       RANK: {rank}" if rank is not None else "")
            w = draw.textlength(combined, font=font)
            draw.text((950 - w, 40), combined, font=font, fill=text_color, stroke_width=1, stroke_fill=(0, 0, 0))
            draw.text((330, 130), username, font=font, fill=text_color, stroke_width=1, stroke_fill=(0, 0, 0))

            exp_str = f"{RankCard._convert_number(current_exp)}/{RankCard._convert_number(max_exp)}"
            w = draw.textlength(exp_str, font=font)
            draw.text((950 - w, 130), exp_str, font=font, fill=text_color, stroke_width=1, stroke_fill=(0, 0, 0))

            bar_exp = max((current_exp / max_exp) * 619, 50)
            im = Image.new("RGBA", (620, 51))
            d = ImageDraw.Draw(im, "RGBA")
            d.rounded_rectangle((0, 0, 619, 50), 30, fill=(255, 255, 255, 225))
            d.rounded_rectangle((0, 0, bar_exp, 50), 30, fill=bar_color)
            background.paste(im, (330, 235))

            image = BytesIO()
            background.save(image, 'PNG')
            image.seek(0)
            return image

        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            return await loop.run_in_executor(pool, _process, bg, av)
