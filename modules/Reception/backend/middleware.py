'''
    Handles data flow about projects in general.

    2019-20 Benjamin Kellenberger
'''

from psycopg2 import sql
from modules.Database.app import Database
from util.helpers import current_time


class ReceptionMiddleware:

    def __init__(self, config):
        self.config = config
        self.dbConnector = Database(config)


    def get_project_info(self, username=None, isSuperUser=False):
        '''
            Returns metadata about projects:
            - names
            - links to interface (if user is authenticated)
            - requests for authentication (else)    TODO
            - links to stats and review page (if admin) TODO
            - etc.
        '''
        now = current_time()

        if isSuperUser:
            authStr = sql.SQL('')
            queryVals = None
        elif username is not None:
            authStr = sql.SQL('WHERE username = %s OR demoMode = TRUE OR isPublic = TRUE')
            queryVals = (username,)
        else:
            authStr = sql.SQL('WHERE demoMode = TRUE OR isPublic = TRUE')
            queryVals = None
        
        queryStr = sql.SQL('''SELECT shortname, name, description, username, isAdmin,
            admitted_until, blocked_until,
            annotationType, predictionType, isPublic, demoMode, interface_enabled, ai_model_enabled
            FROM aide_admin.project AS proj
            FULL OUTER JOIN (SELECT * FROM aide_admin.authentication
            ) AS auth ON proj.shortname = auth.project
            {authStr};
        ''').format(authStr=authStr)

        result = self.dbConnector.execute(queryStr, queryVals, 'all')
        response = {}
        for r in result:
            projShort = r['shortname']
            if not projShort in response:
                userAdmitted = True
                if r['admitted_until'] is not None and r['admitted_until'] < now:
                    userAdmitted = False
                if r['blocked_until'] is not None and r['blocked_until'] >= now:
                    userAdmitted = False
                response[projShort] = {
                    'name': r['name'],
                    'description': r['description'],
                    'annotationType': r['annotationtype'],
                    'predictionType': r['predictiontype'],
                    'isPublic': r['ispublic'],
                    'demoMode': r['demomode'],
                    'interfaceEnabled': r['interface_enabled'],
                    'aiModelEnabled': r['ai_model_enabled'],
                    'userAdmitted': userAdmitted
                }
            if isSuperUser:
                response[projShort]['role'] = 'super user'
            elif username is not None and r['username'] == username:
                if r['isadmin']:
                    response[projShort]['role'] = 'admin'
                else:
                    response[projShort]['role'] = 'member'
        
        return response

    
    def enroll_in_project(self, project, username, secretToken=None):
        '''
            Adds the user to the project if it allows arbitrary
            users to join. Returns True if this succeeded, else
            False.
        '''
        try:
            # check if project is public, and whether user is already member of it
            queryStr = sql.SQL('''SELECT isPublic, secret_token
            FROM aide_admin.project
            WHERE shortname = %s;
            ''')
            result = self.dbConnector.execute(queryStr, (project,), 1)

            # only allow enrolment if project is public, or else if secret tokens match
            if not len(result):
                return False
            elif not result[0]['ispublic']:
                # check if secret tokens match
                if secretToken is None or secretToken != result[0]['secret_token']:
                    return False
            
            # add user
            queryStr = '''INSERT INTO aide_admin.authentication (username, project, isAdmin)
            VALUES (%s, %s, FALSE)
            ON CONFLICT (username, project) DO NOTHING;
            '''
            self.dbConnector.execute(queryStr, (username,project,), None)
            return True
        except Exception as e:
            print(e)
            return False