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

import os
import logging

import requests
from flask import Flask, render_template, request, Response
from google.appengine.api import app_identity
from google.appengine.ext import ndb
import cloudstorage as gcs


app = Flask(__name__)


bucket_name = os.environ.get('BUCKET_NAME', app_identity.get_default_gcs_bucket_name())


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
                recordingStatusCallback="call_status"
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


@app.route('/call_status', methods=['POST'])
def receive_recording(**kwargs):
    call_sid = request.form.get("CallSid")
    recording_url = request.form.get("RecordingUrl")
    recording_status = request.form.get("RecordingStatus")
    google_storage_uri = save_to_google_storage(recording_url)
    # transcript = recognize_speech(google_storage_uri)

    logging.info("Call Status: {}, {}, {}".format(call_sid, recording_url, recording_status))

    ancestor_key = ndb.Key("CallList", "twilio")
    call_records = CallRecord.query(ancestor=ancestor_key).filter(CallRecord.call_sid == call_sid).fetch(1)
    call_record = call_records.pop()

    call_record.recording_url = recording_url
    call_record.google_storage_uri = google_storage_uri
    call_record.recording_status = recording_status
    # call_record.transcript = transcript
    call_record.put()

    xml_response = "<Response></Response>"
    return Response(xml_response, mimetype="text/xml")


@app.route('/call_thank_you', methods=['POST'])
def call_thank_you(**kwargs):

    xml_response = """
        <Response>
            <Say>
                Thank you.
            </Say>
        </Response>
    """
    return Response(xml_response, mimetype="text/xml")


@app.route('/test', methods=['GET'])
def test():
    return save_to_google_storage("https://api.twilio.com/2010-04-01/Accounts/AC4912c84b21c8937090fd5f8cb094614b/Recordings/RE689296f4bf315c064341faa07aa93279")


@app.errorhandler(500)
def server_error(e):
    logging.exception('An error occurred during a request.')
    return 'An internal error occurred.', 500


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


# def recognize_speech(recording_gs_uri):
#     request_payload = {
#         "config": {
#             "encoding": "LINEAR16",
#             "sampleRateHertz": 8000,
#             "languageCode": "en-US",
#             "enableWordTimeOffsets": False
#         },

#         "audio": {
#             "uri": recording_gs_uri
#         }
#     }
