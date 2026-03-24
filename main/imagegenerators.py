from django.conf import settings
from imagekit import ImageSpec, register
from imagekit.processors import ResizeToFit, Transpose


class OrientedThumbnail(ImageSpec):
    format = getattr(settings, "IMAGEKIT_DEFAULT_THUMBNAIL_FORMAT", None)

    def __init__(self, width=None, height=None, **kwargs):
        self.processors = [
            Transpose(Transpose.AUTO),
            ResizeToFit(width=width, height=height),
        ]
        super().__init__(**kwargs)


register.generator("main:oriented_thumbnail", OrientedThumbnail)
