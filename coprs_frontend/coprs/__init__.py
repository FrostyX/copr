from __future__ import with_statement

import os
import flask

from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.openid import OpenID

app = flask.Flask(__name__)

if 'COPRS_ENVIRON_PRODUCTION' in os.environ:
    app.config.from_object('coprs.config.ProductionConfig')
elif 'COPRS_ENVIRON_UNITTEST' in os.environ:
    app.config.from_object('coprs.config.UnitTestConfig')
else:
    app.config.from_object('coprs.config.DevelopmentConfig')

oid = OpenID(app, app.config['OPENID_STORE'])
db = SQLAlchemy(app)

import coprs.filters
import coprs.log
import coprs.models

from coprs.views import coprs_ns
from coprs.views.coprs_ns import coprs_builds
from coprs.views.coprs_ns import coprs_general
from coprs.views import backend_ns
from coprs.views.backend_ns import backend_general
from coprs.views import misc

app.register_blueprint(coprs_ns.coprs_ns)
app.register_blueprint(misc.misc)
app.register_blueprint(backend_ns.backend_ns)

app.add_url_rule('/', 'coprs_ns.coprs_show', coprs_general.coprs_show)
