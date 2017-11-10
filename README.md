# flask-gcloud-app

All if this is based off the [Google App Python Standard Env Tutorial](https://cloud.google.com/appengine/docs/standard/python/getting-started/python-standard-env)

1. Create a virtualenv and activate it.
2. `pip install -t lib -r requirements.txt`
3. `dev_appserver.py --host 0.0.0.0 app.yaml`
   The `dev_appserver.py` is something that comes with the Gcloud SDK Python tools
   You should be able to browse to `http://<localhost or computer ip>:8080/form`
   and submit a form and view the result.
4. `gcloud app deploy`
   You should then be able to browse to `https://<google-app-namespace>/form`
