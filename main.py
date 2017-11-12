import os
import logging
import ConfigParser

import json
import requests
from flask import Flask, render_template, request, Response
from google.appengine.api import app_identity
from google.appengine.ext import ndb
import cloudstorage as gcs

## //\\ App Initialization //\\ ##
app = Flask(__name__)
config = ConfigParser.RawConfigParser()
try:
  config.read('app.cfg')
except Exception as e:
  logging.warn("** There was an exception while parsing the app.cfg config file **")
  logging.warn(e)

## //\\//\\ Google Services //\\//\\ ##
bucket_name = os.environ.get('BUCKET_NAME', app_identity.get_default_gcs_bucket_name())
bucket_name = os.environ.get('BUCKET_NAME', app_identity.get_default_gcs_bucket_name())
try:
  with open("access-token", "r") as access_token_file:
    access_token = access_token_file.read().strip()
except IOError as ioe:
  logging.warn("** There is no access_token; you will not be able to use certain features. **")

## //\\//\\ Twilio Services //\\//\\ ##
twilio_number = config.get('Twilio', 'number')
nist_formatted_twilio_number = twilio_number = config.get('Twilio', 'nist_number')
twilio_number = "+11234567890"
nist_formatted_twilio_number = "+1 (123) 456-7890"

## //\\//\\//\\ Index //\\//\\///\\ ##
@app.route('/', methods=['GET'])
def index():
  return render_template("index.html", twilio_number=twilio_number, nist_formatted_twilio_number=nist_formatted_twilio_number)


## //\\//\\//\\ HTML5 Playground //\\//\\///\\ ##
@app.route('/html5', methods=['GET'])
def html5():
    return render_template("html5.html")


## TODO: dpf.2017.11.11 - Move functional pieces out of main.py into own files then modules.
## //\\//\\//\\ Messaging and Calling //\\///\\//\\ ##
class Message(ndb.Model):
    sender_number = ndb.StringProperty()
    content = ndb.StringProperty()
    date = ndb.DateTimeProperty(auto_now_add=True)


class CallRecord(ndb.Model):
    call_sid = ndb.StringProperty()
    caller_number = ndb.StringProperty()
    recording_url = ndb.StringProperty()
    google_storage_uri = ndb.StringProperty()
    recording_status = ndb.StringProperty()
    transcript = ndb.StringProperty()
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
    message_type = request.args.get("type")
    message_type = message_type if message_type is not None else "sms"
    ancestor_key = ndb.Key("MessageList", message_type)
    messages = Message.query(ancestor=ancestor_key).order(-Message.date).fetch(20)

    return render_template(
        "messages.html",
        messages=messages)


@app.route('/sms_message', methods=['POST'])
def receive_sms(**kwargs):
    number = request.form.get("From")
    sms_body = request.form.get("Body")

    message = Message(
        parent=ndb.Key("MessageList", "sms"),
        sender_number=number,
        content=sms_body)
    message.put()

    xml_response = "<Response><Message>Thanks</Message></Response>"
    return Response(xml_response, mimetype="text/xml")


def save_to_google_storage(http_file_uri):
    local_filename = http_file_uri.split("/").pop()
    local_filepath = "/{}/{}".format(bucket_name, local_filename)
    logging.info(http_file_uri)
    logging.info(local_filename)
    r = requests.get(http_file_uri, stream=True)
    with gcs.open(local_filepath, "w", content_type="binary/octet-stream") as gcs_file:
        for chunk in r.iter_content(chunk_size=1024):
            gcs_file.write(chunk)

    return "gs://{}/{}".format(bucket_name, local_filename)


def recognize_speech(recording_gs_uri):
    request_headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer {}".format(access_token)
    }
    request_payload = {
        "config": {
            "encoding": "LINEAR16",
            "sampleRateHertz": 8000,
            "languageCode": "en-US",
            "enableWordTimeOffsets": False
        },

        "audio": {
            "uri": recording_gs_uri
        }
    }
    response = requests.post("https://speech.googleapis.com/v1/speech:recognize", data=json.dumps(request_payload), headers=request_headers)
    response_json = response.json()
    result = response_json.get("results").pop()
    alternatives = sorted(result.get("alternatives"), key=lambda alternative: alternative["confidence"])
    if len(alternatives) > 0:
        return alternatives[0]["transcript"]

    return None


## //\\//\\ Errors //\\//\\ ##
@app.errorhandler(500)
def server_error(e):
    logging.exception('An error occurred during a request.')
    return 'An internal error occurred.', 500
