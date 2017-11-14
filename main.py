## TODO: dpf.2017.11.11 - Move functional pieces out of main.py into own files then modules.
import ConfigParser
import json
import logging
import os
import re

from flask import Flask, render_template, request, Response
from google.appengine.api import app_identity
from google.appengine.ext import ndb
from twilio.rest import Client
import cloudstorage as gcs
import requests

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
twilio_number = ""
nist_formatted_twilio_number = ""
twilio_account_sid = ""
twilio_auth_token = ""
phone_numbers = []
if config.has_section('Twilio'):
  if config.has_option('Twilio', 'number'):
    twilio_number = config.get('Twilio', 'number')
  if config.has_option('Twilio', 'nist_number'):
    nist_formatted_twilio_number = config.get('Twilio', 'nist_number')
  if config.has_option('Twilio', 'account_sid'):
    twilio_account_sid = config.get('Twilio', 'account_sid')
  if config.has_option('Twilio', 'auth_token'):
    twilio_auth_token = config.get('Twilio', 'auth_token')
  if config.has_option('Twilio', 'phone_numbers'):
    phone_numbers = config.get('Twilio', 'phone_numbers')
else:
  logging.warn('** Twilio section is missing from config. Twilio features will not work. **')

## //\\//\\ Slack Services //\\//\\ ##
slack_bot_api_token = ""
slack_general_channel_id = ""
if config.has_section('Slack'):
  if config.has_option('Slack', 'bot_api_token'):
    slack_bot_api_token = config.get('Slack', 'bot_api_token')
  if config.has_option('Slack', 'general_channel_id'):
    slack_general_channel_id = config.get('Slack', 'general_channel_id')
else:
  logging.warn("** There is no Slack config. Slack features will not be usable. **")


## //\\//\\//\\ Index //\\//\\///\\ ##
@app.route('/', methods=['GET'])
def index():
  logging.info('phone numbers: %s', phone_numbers)
  return render_template("index.html", twilio_number=twilio_number, nist_formatted_twilio_number=nist_formatted_twilio_number)


## //\\//\\//\\ HTML5 Playground //\\//\\///\\ ##
@app.route('/html5', methods=['GET'])
def html5():
    return render_template("html5.html")


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


## //\\//\\//\\//\\ Messages //\\//\\///\\//\\ ##
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
    logging.info("sms_message: POST : request.form =  %s", request.form)
    number = request.form.get("From")
    sms_body = request.form.get("Body")
    sms_num_media = request.form.get("NumMedia")
    if sms_num_media:
      sms_num_media = int(sms_num_media)
    media_urls_xml = ""
    if sms_num_media > 0:
      media_urls = [request.form.get("MediaUrl" + str(i)) for i in range(sms_num_media)]
      media_urls_xml = ''.join(["<Media>{}</Media>".format(mu) for mu in media_urls])
    sc_url = ""
    if "SC:" in sms_body:
      links = re.findall(r'SC:\((\S*)\):CS', sms_body)
      sc_url = ' '.join(links)
    if sc_url:
      client = Client(twilio_account_sid, twilio_auth_token)
      for ph_num in phone_numbers:
        client.messages.create(to=ph_num,
            from_=twilio_number,
            body="Check out some jams: {}".format(sc_url),
            media_url=None)
    if sms_body.index('IDEA:') == 0:
      # post the id in slack channel
      data = {
          'channel': slack_general_channel_id,
          'text': sms_body,
          'as_user': True
          }
      headers = {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + slack_bot_api_token
          }
      r = requests.post('https://slack.com/api/chat.postMessage', headers=headers, data=json.dumps(data))
      logging.info('Slack response status code: %s', r.status_code)
      logging.info('Slack response: %s', json.dumps(r.json(), indent=4, sort_keys=True))
    message = Message(
        parent=ndb.Key("MessageList", "sms"),
        sender_number=number,
        content=sms_body)
    message.put()

    xml_response = "<Response><Message><Body>Thanks</Body>%s</Message></Response>" % media_urls_xml
    return Response(xml_response, mimetype="text/xml")


## //\\//\\//\\//\\ Calls //\\//\\///\\//\\ ##
@app.route('/calls', methods=['POST'])
def receive_call(**kwargs):
  call_sid = request.form.get("CallSid")
  caller_number = request.form.get("From")

  call_record = CallRecord(
    parent=ndb.Key("CallList", "twilio"),
    call_sid=call_sid,
    caller_number=caller_number)
  call_record.put()

  xml_response = """
    <Response>
      <Say>
        Please leave a message at the beep.
        Press the star key when finished.
      </Say>
      <Record
        action="call_thank_you"
        recordingStatusCallback="receive_recording"
        method="GET"
        maxLength="20"
        finishOnKey="*"
      />
      <Say>I did not receive a recording.</Say>
    </Response>
  """
  return Response(xml_response, mimetype="text/xml")


@app.route('/calls', methods=['GET'])
def list_calls(**kwargs):
  ancestor_key = ndb.Key("CallList", "twilio")
  call_records = CallRecord.query(ancestor=ancestor_key).order(-CallRecord.date).fetch(20)
  return render_template("incoming_calls.html", call_records=call_records)


@app.route('/receive_recording', methods=['POST'])
def receive_recording(**kwargs):
  call_sid = request.form.get("CallSid")
  recording_url = request.form.get("RecordingUrl")
  recording_status = request.form.get("RecordingStatus")
  google_storage_uri = save_to_google_storage(recording_url)
  transcript = recognize_speech(google_storage_uri)
  logging.info("Transcript: {}".format(transcript))

  logging.info("Call Status: {}, {}, {}".format(call_sid, recording_url, recording_status))

  ancestor_key = ndb.Key("CallList", "twilio")
  call_records = CallRecord.query(ancestor=ancestor_key).filter(CallRecord.call_sid == call_sid).fetch(1)
call_record = call_records.pop()

  call_record.recording_url = recording_url
  call_record.google_storage_uri = google_storage_uri
  call_record.recording_status = recording_status
  call_record.transcript = transcript
  call_record.put()

  xml_response = "<Response><Say>Thank you.</Say></Response>"
  return Response(xml_response, mimetype="text/xml")


@app.route('/call_thank_you', methods=['GET'])
def call_thank_you(**kwargs):
  xml_response = """
    <Response>
      <Say>
        Thank you.
      </Say>
    </Response>
  """
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
