#!/usr/bin/env python
import os
from flask import Flask, jsonify, make_response, g
from flask.ext.httpauth import HTTPBasicAuth
from sqlalchemy.orm import validates
from flask.ext.restful import Resource
from flask.ext.sqlalchemy import SQLAlchemy
from passlib.apps import custom_app_context as pwd_context
from itsdangerous import (TimedJSONWebSignatureSerializer
                          as Serializer, BadSignature, SignatureExpired)
from vyos_session import utils
import logging
from logging.handlers import RotatingFileHandler
import re

logger = logging.getLogger(__name__)
utils.init_logger(logger)

## initialization ##

app = Flask('pyatta')
auth = HTTPBasicAuth()
db = SQLAlchemy(app)

app.config.update(
    DEBUG = bool(utils.get_config_params('api','debug')),
    SECRET_KEY = utils.get_config_params('api_auth','secret_key'),
)

# Logging api activities to a file instead of stdout (default)
# to see the log messages emitted by Werkzeug.
# TODO : test log file existance
# NOTE : this will not be valide in production environment because the log will be managed by apache server
handler = RotatingFileHandler('/var/log/pyatta/pyatta_api.log', maxBytes=10000, backupCount=1)
handler.setLevel(logging.INFO)
log = logging.getLogger('werkzeug')
log.setLevel(logging.DEBUG)
log.addHandler(handler)

def check_db_config():
    """
    Check Database configuration
    """
    db_driver = utils.get_config_params('sql','driver')
    db_uri = utils.get_config_params('sql','db_uri')
    logger.debug('Database driver : "%s"' % db_driver)
    logger.debug('Database URI : "%s"' % db_uri)

    if db_driver == 'sqlite':
        slash_postion = db_uri.find(':///')
        if slash_postion == -1:
            logger.error('Incorrect Database URI.')
            return False
        if not db_uri[:slash_postion] == 'sqlite':
            logger.error('Database driver not supported')
            return False
        if not os.path.isfile(db_uri[slash_postion+4:]):
            logger.error('SQLite database file not found')
            return False
        app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
        if bool(utils.get_config_params('sql','commit_on_teardown')):
            app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
        logger.info('Database configuration is OK')
        return True
    logger.error('Database driver not supported')
    return False

class UserAttributeNotValide(Exception): pass

class User(db.Model):
    """
    This class provides the database schema whereas 
    other methods are needed for authentication
    """
    error_msg=""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), nullable=False, unique=True)
    password = db.Column(db.String(64), nullable=False)
    email = db.Column(db.String(32), nullable=False, unique=True)
    superuser=db.Column(db.Boolean, nullable=False, default=0)

    @validates('username', 'email', 'password', 'superuser')
    def validate_user_attributes(self, key, attribute):
        if key == 'username':
            if len(attribute) < 5 : raise UserAttributeNotValide('username not valide')
        if key == 'password':
            if len(attribute) < 5 or attribute == self.username :
                raise UserAttributeNotValide('password not valide')
            attribute = pwd_context.encrypt(attribute)
        if key == 'email':
            pattern = '[\.\w]{1,}[@]\w+[.]\w+'
            if not re.match(pattern, attribute): raise UserAttributeNotValide('email not valide')
        if key == 'superuser':
            if attribute not in ['0','1']: raise UserAttributeNotValide('superuser value not valide')
        return attribute

    def verify_password(self, password):
        """
        This method checks if the password provided as input is valid
        """
        return pwd_context.verify(password, self.password)
    
    def generate_auth_token(self, expiration=600):
        """
        This method generates a temporary token needed for authentication
        """
        s = Serializer(app.config['SECRET_KEY'], expires_in=expiration)
        return s.dumps({'id': self.id})

    @staticmethod
    def verify_auth_token(token):
        """
        This method check if a given token still valid or not
        """
        s = Serializer(app.config['SECRET_KEY'])
        try:
            data = s.loads(token)
        except (SignatureExpired, BadSignature):
            # SignatureExpired => valid token, but expired
            # BadSignature => invalid token
            return False
        user = User.query.get(data['id'])
        return user

class TokenResource(Resource):
    """
    This class allows temporary token generation
    """
    decorators = [auth.login_required]

    def get(self):
        #this token will be valid for 60 seconds
        token = g.user.generate_auth_token(60)    
        return {'token': token.decode('ascii'), 'duration': 60}, 201

@auth.error_handler
def unauthorized():
    """
    This method handles error returned with code 403
    """
    logger.error('Unauthorized access !')
    # return 403 instead of 401 to prevent browsers from displaying the default auth dialog
    return make_response(jsonify({'error':'Unauthorized access !', 'reason':User.error_msg }), 403)

@auth.verify_password
def verify_password(username_or_token, password):
    """
    This method is invoked when a request was sent and contains authentication elements
    """
    logger.info("======> Checking user cridentials...")
    # first try to authenticate by token
    if password == 'unused':
        user = User.verify_auth_token(username_or_token)
        if not user:
            User.error_msg="invalid token!"
            return False
    # try to authenticate with username/password
    else:
        user = User.query.filter_by(username=username_or_token).first()
        if not user or not user.verify_password(password):
            User.error_msg="username/password error!"
            return False

    g.user = user
    return True

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error':'Resource not found'}), 404
