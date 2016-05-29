from flask import Flask, request, abort
from telegram_handler import done_img
import json


app = Flask(__name__)


@app.route('/', methods=['POST'])
def hello_world():
    if not request.json or 'status' not in request.json or request.json['status'] != 'done'\
            or 'id' not in request.json:
        abort(400)
    img_id = request.json['id']
    done_img(img_id)
    return json.dumps({'success':True}), 200, {'ContentType':'application/json'}
