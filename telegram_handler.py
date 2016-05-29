import urllib
from config import *
import os
import requests
import telegram
import json
from PIL import Image
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

import logging

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)


t_bot = telegram.Bot(BOT_TOKEN)


class ImgRequest:
    def __init__(self, id_request):
        self.id_request = id_request
        #0 - is not set
        #1 - waiting
        #2 - set
        self.got_img = 0
        self.got_style = 0
        self.img_token = None
        self.style_token = None
        self.queue_id = None

    def download_img(self):
        img_file = t_bot.getFile(self.img_token)
        img_file_name = 'tmp/' + self.img_token + '.jpg'
        img_file.download(img_file_name)

    def download_style(self):
        style_file_name = 'tmp/' + self.style_token + '.jpg'
        style_file = t_bot.getFile(self.style_token)
        style_file.download(style_file_name)

    def set_img(self,  token):
        if self.got_img == 3:
            os.remove('tmp/' + self.img_token + '.jpg')
        self.img_token = token
        self.got_img = 2
        try:
            self.download_img()
        except Exception as err:
            raise err
        self.got_img = 3
        if self.got_style == 3:
            self.process_images()

    def set_style(self, token):
        if self.got_style == 3:
            os.remove('tmp/' + self.style_token + '.jpg')
        self.style_token = token
        self.got_style = 2
        try:
            self.download_style()
        except Exception as err:
            raise err
        self.got_style = 3
        if self.got_img == 3:
            self.process_images()

    def process_images(self):
        img_file_name = 'tmp/' + self.img_token + '.jpg'
        style_file_name = 'tmp/' + self.style_token + '.jpg'
        files = {'style': open(style_file_name, 'rb'),
                 'subject': open(img_file_name, 'rb')}
        print('Sending...')
        r = requests.post(NEURAL_API_HOST + '/api/image', files=files, data={'args': json.dumps({'iterations':50,
                                                                             'back_host': THIS_HOST})})
        print(r.text)
        if 'id' in r.json():
            self.queue_id = r.json()['id']
            print(self.queue_id)
        else:
            raise ValueError('Oops')


class Client:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.requests = {}
        self.num_requests = 0

    def new_request(self):
        cur_num = self.num_requests
        self.num_requests += 1
        self.requests[cur_num] = ImgRequest(cur_num)
        return self.requests[cur_num]

    def last_request(self):
        if self.num_requests == 0:
            return None
        return self.requests[self.num_requests - 1]


clients = {}
uuids = {}


def done_img(img_id):
    urllib.urlretrieve(NEURAL_API_HOST + '/api/image/' + str(img_id), 'tmp/' + str(img_id) + '.jpg')
    client_id, img_num = uuids[img_id]
    t_bot.sendMessage(client_id, text='Your image #{}'.format(img_num))
    t_bot.sendPhoto(client_id, open('tmp/' + str(img_id) + '.jpg', 'rb'))


def start(bot, update):
    bot.sendMessage(update.message.chat_id, text='Hi! Use /new to process a new image')
    chat_id = update.message.chat_id
    clients[chat_id] = Client(chat_id)


def process_image(bot, update):
    chat_id = update.message.chat_id
    bot.sendMessage(update.message.chat_id, text='Well, now send me an image')
    if chat_id not in clients:
        clients[chat_id] = Client(chat_id)
    clients[chat_id].new_request()
    request = clients[chat_id].last_request().got_img = 1


def got_img(bot, update):
    chat_id = update.message.chat_id
    img = update.message.photo
    img_token = None
    for ph in img:
        if ph.width < 700 and ph.height < 700:
            img_token = ph.file_id
    if not img_token:
        bot.sendMessage(update.message.chat_id, text='Image must be less than 700x700!')
        return
    request = clients[chat_id].last_request()
    if request and request.got_img != 0:
        if request.got_img != 3:
            request.set_img(img_token)
            bot.sendMessage(update.message.chat_id, text='Great! Now send me a style')
            #except Exception as e:
            #    bot.sendMessage(update.message.chat_id, text=e.message)
        else:
            if request.got_style != 3:
                request.set_style(img_token)
                uuids[clients[chat_id].last_request().queue_id] = (chat_id, clients[chat_id].num_requests - 1, )
                bot.sendMessage(update.message.chat_id, text="Ok, images are in processing now. "
                                                            "You'll get a result when it is done")
                bot.sendMessage(update.message.chat_id, text="Your image's id is {}. You can use /status"
                                                            " with id to get your image's status".format(clients[chat_id].num_requests - 1))


def error(bot, update, error):
    logger.warn('Update "%s" caused error "%s"' % (update, error))


def status(bot, update):
    chat_id = update.message.chat_id
    if chat_id not in clients:
        clients[chat_id] = Client(chat_id)
    if clients[chat_id].num_requests == 0:
        bot.sendMessage(update.message.chat_id, text='You have no images in processing')
        return
    mes = update.message.text.split()
    id = 0
    if len(mes) == 1:
        id = clients[chat_id].num_requests - 1
    else:
        id = mes[1]
        if mes[1].isnumeric():
            id = int(id)

    if id not in clients[chat_id].requests:
        bot.sendMessage(update.message.chat_id, text='You have no such image')
        return

    r = requests.get(NEURAL_API_HOST + '/api/image/' + clients[chat_id].requests[id].queue_id + '/status')
    print(r.json())
    if r.json()['status'] == 'queued' or r.json()['status'] == 'initializing':
        bot.sendMessage(update.message.chat_id, text='This image is in queue')
    elif r.json()['status'] == 'done':
        bot.sendMessage(update.message.chat_id, text='This image is done')
    else:
        proc = int(100 * r.json()['done_iterations'] / r.json()['iterations_number'])
        bot.sendMessage(update.message.chat_id, text='Processed {}%'.format(proc))

def delete(bot, update):
    chat_id = update.message.chat_id
    if chat_id not in clients:
        clients[chat_id] = Client(chat_id)
    if clients[chat_id].num_requests == 0:
        bot.sendMessage(update.message.chat_id, text='You have no images in processing')
        return
    mes = update.message.text.split()
    id = 0
    if len(mes) == 1:
        id = clients[chat_id].num_requests - 1
    else:
        id = mes[1]
        if mes[1].isnumeric():
            id = int(id)

    if id not in clients[chat_id].requests:
        bot.sendMessage(update.message.chat_id, text='You have no such image')
        return

    r = requests.delete(NEURAL_API_HOST + '/api/image/' + clients[chat_id].requests[id].queue_id)
    bot.sendMessage(update.message.chat_id, text='Image #{} was deleted!'.format(id))
    del clients[chat_id].requests[id]


def start_bot():
    updater = Updater(BOT_TOKEN)
    dp = updater.dispatcher
    dp.addHandler(CommandHandler("start", start))
    dp.addHandler(CommandHandler("new", process_image))
    dp.addHandler(CommandHandler("status", status))
    dp.addHandler(CommandHandler("delete", delete))
    dp.addHandler(MessageHandler([Filters.photo], got_img))
    dp.addErrorHandler(error)
    updater.start_polling()
