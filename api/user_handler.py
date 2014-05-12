#!/usr/bin/env python

from flask import abort
from flask.ext.restful import Resource, reqparse, fields, marshal
from sqlalchemy import update
from base_setup import auth, db, User

user_fields = {
    'username':fields.String,
    'email':fields.String,
    'superuser':fields.Boolean,
    'uri':fields.Url('user')
}

class UsersResource(Resource):
    """
    This class shows users and may delete or add new others
    """
    decorators = [auth.login_required]

    def __init__(self):
        """
        This constructor defines parser for incoming users requests
        """
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument('username', type=str, required=True, help='No username provided', location='json')
        self.reqparse.add_argument('password', type=str, required=True,help='No password provided', location='json')
        self.reqparse.add_argument('email', type=str, default="", location='json')
        self.reqparse.add_argument('superuser', type=int, required=True,help='No superuser privilege provided', location='json')
        super(UsersResource, self).__init__()

    def get(self):
        """
        This method returns informations concerning existing users
        """
        return { 'users': map(lambda t: marshal(t, user_fields), User.query.all()) }

    def post(self):
        """
        This method allows the creation of new users
        """
        args = self.reqparse.parse_args()
        if User.query.filter_by(username=args['username']).first() is not None:
            return {'error':'username name already allocated!'}, 400
        user = User(username=args['username'])
        user.hash_password(args['password'])
        user.set_email(args['email'])
        user.set_superuser(args['superuser'])
        db.session.add(user)
        db.session.commit()
        return { 'user': marshal(user, user_fields) }, 201

class UserResource(Resource):
    """
    This class implements the get, edit and delete methods of a specific user
    """
    decorators = [auth.login_required]
    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument('username', type = str, location = 'json')
        self.reqparse.add_argument('password', type = str, location = 'json')
        self.reqparse.add_argument('email', type = str , location = 'json')
        super(UserResource, self).__init__()

    def get(self, id):
        """
        This method returns user informations for a given id
        """
        user = User.query.get(id)
        if not user:
            abort(404)
        return { 'user': marshal(user, user_fields) }

    def put(self, id):
        """
        This method edit existing informations of a particular user
        """
        user = User.query.get(id)
        if not user:
            abort(404)
        args = self.reqparse.parse_args()
        if args['password']:
            args['password']=pwd_context.encrypt(args['password'])
        for cle in ['username','password','email']:
            if args[cle]:
                #get new updated informations and set it to the appropriate record
                user=User.query.filter_by(id=id).update({cle:args[cle]})
        db.session.commit()
        return {'user':'edited successfully!'}, 200
        #return { 'user': marshal(user, user_fields) }

    def delete(self, id):
        """
        This method may delete an existing user
        """
        user = User.query.get(id)
        if not user:
            abort(404)
        db.session.delete(user)
        db.session.commit()
        return { 'Info': 'mentioned user has been deleted successfully!'}
