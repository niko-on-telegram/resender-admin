from aiogram.types import MessageEntity

from resender_bot.handlers.base_handlers import extract_text


def test_extract_from_entity():
    ents = [
        MessageEntity(type="url", offset=24, length=195),
        MessageEntity(type="url", offset=246, length=96),
    ]
    text = ('test message with image https://login.sendpulse.com/api/telegram-service/guest/messages/media/?bot_id\
=66afa76f9d954f1cb8000d12&file_id=AgACAgQAAxkBAAEBrB1mvxG8X70KlehZZ-1-vPey03y4xwAC6cExG46R\
-FFMGYDaxo0b3QEAAwIAA3gAAzUE\n\n\ntest message with video \
https://file-examples.com/storage/feaf6fc38466e98369950a4/2017/04/file_example_MP4_480_1_5MG.mp4'
            'abacaba')
    cleared_text, links = extract_text(text, ents)
    assert cleared_text == 'test message with image \n\n\ntest message with video abacaba'
    assert links == [ents[0].extract_from(text), ents[1].extract_from(text)]
