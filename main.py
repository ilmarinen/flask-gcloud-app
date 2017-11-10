# Copyright 2016 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging

from flask import Flask, render_template, request, Response
from google.appengine.ext import ndb


app = Flask(__name__)


class Message(ndb.Model):
    sender_number = ndb.StringProperty()
    content = ndb.StringProperty()
    date = ndb.DateTimeProperty(auto_now_add=True)


@app.route('/form')
def form():
    return render_template('form.html')


@app.route('/submitted', methods=['POST'])
def submitted_form():
    number = request.form['number']
    message = request.form['message']
    sms_message = Message(
        parent=ndb.Key("MessageList", "form"),
        sender_number=number,
        content=message)
    sms_message.put()

    return render_template(
        'submitted_form.html',
        number=number,
        message=message)


@app.route('/messages', methods=['GET'])
def messages():
    ancestor_key = ndb.Key("MessageList", "form")
    messages = Message.query(ancestor=ancestor_key).order(-Message.date).fetch(20)

    return render_template(
        "messages.html",
        messages=messages)


@app.errorhandler(500)
def server_error(e):
    logging.exception('An error occurred during a request.')
    return 'An internal error occurred.', 500
